# encoding: utf-8
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
    ContextTypes,
    ConversationHandler
)
from telegram import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
    Bot,
)
from psutil import *
import atexit
import subprocess
import telegram
import os
import threading
import time
import datetime
import shutil
import uuid
import yaml
import sys
import random
import cv2
import queue


def transport_video_to_telegram(rtsp_addr, video_dir, video_name, uuid_name):
    global task_in_progress_num
    while True:
        try:
            logprint(f"正在上传：{video_name}")
            try:
                device_name = rtsp_addr[rtsp_addr.find('@127.0.0.1:') + 11:].replace('/', 'G')
                video_name_list = video_name.split(' ')
                ymd_list = video_name_list[0].split('-')
                ymd_text = f"{ymd_list[0]}-{ymd_list[1]}-{ymd_list[2]}"
                ymd_text_cn = f"{ymd_list[0]}年{ymd_list[1]}月{ymd_list[2]}日"
                hms_list = video_name_list[1].split('.')[0].split(':')
                hms_text = f"{hms_list[0]}:{hms_list[1]}:{hms_list[2]}"
                hms_text_cn = f"{hms_list[0]}时{hms_list[1]}分{hms_list[2]}秒"
            except:
                logprint("时间格式化出现错误...", 'ERROR')
                time.sleep(1)
                continue
            text = f"设备名称： #{device_name}\n录像名称：`{video_name.replace(' ', '-').replace(':', '-')}`\n数字时间： `{ymd_text}` `{hms_text}`\n中文时间： `{ymd_text_cn}` `{hms_text_cn}`\nrtsp地址：`{rtsp_addr}`\nUUID：`{uuid_name}`"
            bot.sendMediaGroup(chat_id=tg_chat_id,
                               media=[telegram.InputMediaVideo(open(video_dir, 'rb'), caption=text,
                                                               parse_mode="Markdown")])
            os.remove(video_dir)
            logprint(f"上传成功：{video_name}")
            task_in_progress_num -= 1
            break
        except:
            logprint(f"上传失败：{video_name}，准备重新上传...", "ERROR")
            time.sleep(random.randint(1, 30))
            continue


def queue_to_upload_video():
    global download_queue
    global task_in_queue_num
    global task_in_progress_num
    while True:
        while not download_queue.empty():
            rtsp_addr2, todir2, video_name2, uuid_name2 = download_queue.get()
            while True:
                if task_in_progress_num < max_tasks_num:
                    task_in_progress_num += 1
                    task_in_queue_num -= 1
                    threading.Thread(name=uuid_name2 + "transport_video_to_telegram",
                                     target=transport_video_to_telegram,
                                     args=(rtsp_addr2, todir2, video_name2, uuid_name2)).start()
                    break
                else:
                    time.sleep(1)
        time.sleep(1)


def check_connection(test_connection_rtsp_url):
    global is_connected
    global is_connected_text
    global closed_connection_time
    global closed_frequency
    isOpened = cv2.VideoCapture(test_connection_rtsp_url).isOpened()
    if isOpened != is_connected and not isOpened:
        is_connected = isOpened
        closed_frequency += 1
        closed_connection_time = int(time.time())
        temp_text = f"连接在 `{str(datetime.datetime.now())}` 时断开，请检查网络\n"
        is_connected_text += temp_text
        if forwarding_video:
            mixprint(temp_text.replace('\n', ''), 'WARN', 'Markdown')
    elif isOpened != is_connected and isOpened:
        is_connected = isOpened
        temp_text = f"连接在 `{str(datetime.datetime.now())}` 时恢复，宕机时间：{str(int(time.time()) - closed_connection_time)}秒\n"
        is_connected_text += temp_text
        if forwarding_video:
            mixprint(temp_text.replace('\n', ''), 'INFO', 'Markdown')
    return isOpened


def ffmpeg_download_video(rtsp_addr2, uuid_dir2):
    while True:
        if check_connection(rtsp_addr2) and forwarding_video:
            process_temp = subprocess.Popen(
                f"/usr/bin/ffmpeg -rtsp_transport tcp -re -i \"{rtsp_addr2}\" -vcodec copy -acodec copy -fs 9000k -y \"{uuid_dir2}/{str(uuid.uuid4())}.mkv\"",
                shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            process_temp.wait()
        else:
            time.sleep(5)


def check_file_exist(rtsp_addr, uuid_name):
    global download_queue
    global task_in_queue_num
    last_files = []
    last_veritry = ''
    first_flag = True
    uuid_dir2 = os.getcwd() + "/" + uuid_name
    while True:
        files = os.listdir(uuid_dir2)
        files.remove("temp")
        if files == last_files:
            time.sleep(1)
            continue
        else:
            if first_flag:
                first_flag = False
                try:
                    last_veritry = list(set(files) - set(last_files))
                except:
                    last_files = files
                    time.sleep(1)
                    continue
                last_files = files
                time.sleep(1)
            else:
                try:
                    now_veritry = list(set(files) - set(last_files))
                    if not now_veritry:
                        last_files = files
                        time.sleep(1)
                        continue
                except:
                    last_files = files
                    time.sleep(1)
                    continue
                last_files = files
                print("获取到新文件列表：" + str(now_veritry) + "，上传上一个文件列表：" + str(last_veritry))
                for last_v in last_veritry:
                    video_time = str(datetime.datetime.now())
                    video_time_2 = video_time.replace(':', '-').replace(' ', '-')
                    fordir = uuid_dir2 + "/" + last_v
                    todir = uuid_dir2 + "/temp/" + video_time_2 + ".mp4"
                    video_name = video_time + ".mp4"
                    shutil.move(fordir, todir)
                    download_queue.put((rtsp_addr, todir, video_name, uuid_name))
                    task_in_queue_num += 1
                last_veritry = now_veritry
                time.sleep(1)


def check_time_to_run_code():
    global forwarding_video
    while True:
        global start_time
        global stop_time
        start_time_h, start_time_m = start_time
        stop_time_h, stop_time_m = stop_time
        if str(datetime.datetime.now().hour) == str(int(start_time_h)) and str(datetime.datetime.now().minute) == str(
                int(start_time_m)):
            mixprint("#GCF机器人开始回放上传\nGCF 机器人 - 在 " + start_time_h + ":" + start_time_m + " 由设定的时间自动开始回放上传.")
            forwarding_video = True
        elif str(datetime.datetime.now().hour) == str(int(stop_time_h)) and str(datetime.datetime.now().minute) == str(
                int(stop_time_m)):
            mixprint("#GCF机器人停止回放上传\nGCF 机器人 - 在 " + start_time_h + ":" + start_time_m + " 由设定的时间自动停止回放上传.")
            forwarding_video = False
        time.sleep(59)


def mixprint(msg, state='INFO', parse_mode=None):
    logprint(msg, state)
    dispatcher.bot.send_message(chat_id=tg_chat_id, text=msg, parse_mode=parse_mode)


def mixreplyprint(update, msg, state='INFO', parse_mode=None):
    logprint(msg, state)
    update.message.reply_text(text=msg, parse_mode=parse_mode)


def logprint(msg, state='INFO'):
    print_build_msg = f"[{str(datetime.datetime.now())}] [{state}] " + msg.replace('\n', ' ')
    print(print_build_msg)


def tgprint(msg, parse_mode=None):
    dispatcher.bot.send_message(chat_id=tg_chat_id, text=msg, parse_mode=parse_mode)


def authForUser(update):
    if not str(update.message['from_user']['id']) in tg_owner_id_list:
        update.message.reply_text("你未通过验证，无法使用本机器人!")
        dispatcher.bot.send_message(text=f"""
未验证的用户在未验证的对话中发送了信息.

chat-title: `{update.message['chat']['aaa']}`
chat-type: {update.message['chat']['type']}
chat-id: `{update.message['chat']['id']}`
username: `{update.message['from_user']['username']}`
user-id: `{update.message['from_user']['id']}`
date: {update.message['date']}
text: `{update.message['text']}`

请管理员悉知！
        """, chat_id=tg_owner_id, parse_mode='Markdown')
        return True
    logprint(f"'{update.message.text}' From '{update.message.from_user.username}'")
    return False


def helpness(update: Update, context):
    if authForUser(update):
        return
    mixreplyprint(update, msg="""
欢迎使用 GCF 机器人!

以下是详细命令列表:  
/start 开始
/search 搜索历史回放
/isonline 查看当前在线状态
/runstatus 查看当前运行状态
/offlinetext 查看掉线记录
/setstate 切换视频转发状态
/setmaxthread 设置最大上传线程数
/setruntime 定时开启回放上传
/setrtspaddr 配置rtsp设备地址
/restart 重启 GCF
/shutdown 关闭 GCF
/help 帮助列表
/cancel 取消当前操作
    """)


def start(update: Update, context):
    if authForUser(update):
        return
    start_text = """
欢迎使用 GCF 机器人!
请发送 /help 来获取详细命令列表.
    """
    mixreplyprint(update, start_text)


def search(update: Update, context):
    if authForUser(update):
        return
    device_text = ''
    for device in run_devices:
        device_text += f"\n#{device}"
    mixreplyprint(update, f"""
根据当前连接的设备搜索：{device_text}
——————————
根据日期、时间搜索：
请直接搜索时间，例如：
2022-01-01 00:00:00
或
2022年01月01日 00时00分00秒
    """)


def runstatus(update: Update, context):
    global runstatus_output
    runstatus_output = True
    mixreplyprint(update, f"开始输出运行状态，发送 /cancel 或者任意消息来停止输出.")
    threading.Thread(name=str(uuid.uuid4()) + "-runstatus_thread", target=runstatus_thread,
                     args=(update.message['chat']['id'],
                           dispatcher.bot.send_message(chat_id=update.message['chat']['id'], text=server_msg_text(),
                                                       parse_mode='Markdown').message_id)).start()
    return 1


def runstatus1(update: Update, context):
    global runstatus_output
    runstatus_output = False
    mixreplyprint(update, f"成功停止输出")
    return ConversationHandler.END


def runstatus_thread(chat_id, message_id):
    global runstatus_output
    while True:
        if runstatus_output:
            bot.edit_message_text(text=server_msg_text(), chat_id=chat_id, message_id=message_id, parse_mode='Markdown')
        else:
            return


def server_msg_text():
    sent_before = net_io_counters().bytes_sent
    recv_before = net_io_counters().bytes_recv
    time.sleep(0.1)
    sent_now = net_io_counters().bytes_sent
    recv_now = net_io_counters().bytes_recv
    sent = (sent_now - sent_before) / 0.1 / 1024
    recv = (recv_now - recv_before) / 0.1 / 1024
    list_temp = open("/proc/loadavg").read().split(' ')
    s1min = list_temp[0]
    s5min = list_temp[1]
    s15min = list_temp[2]
    text = f"""
*任务上传情况*
当前连接状态：{'已连接' if is_connected else '未连接'}
视频转发状态：{'正在转发' if forwarding_video else '已停止转发'}
正在上传的任务数：{str(task_in_progress_num)}
在队列中等待的任务数：{str(task_in_queue_num)}
最大同时上传任务数：{str(max_tasks_num)}
当前转发设备数：{str(len(run_devices))}

*服务器运行情况*
负载：{s1min} {s5min} {s15min}
CPU占用：{cpu_percent(interval=1)}%
内存占用：{str(virtual_memory().percent)}%  {str(int((virtual_memory().total - virtual_memory().available) / 1024 / 1024))}M/{str(int(virtual_memory().total / 1024 / 1024))}M
Swap占用：{str(swap_memory().percent)}%  {str(int(swap_memory().used / 1024 / 1024))}M/{str(int(swap_memory().total / 1024 / 1024))}M
上传速度：{"{0}KB/s".format("%.2f" % sent)}
下载速度：{"{0}KB/s".format("%.2f" % recv)}
    """
    return text


def isonline(update: Update, context):
    if authForUser(update):
        return
    if is_connected:
        text_temp = '在线'
    else:
        text_temp = '离线\n离线持续时间：' + str(int(time.time()) - closed_connection_time) + "秒"
    mixreplyprint(update, f"当前连接状态：{text_temp}")


def offlinetext(update: Update, context):
    if authForUser(update):
        return
    if is_connected_text == '':
        mixreplyprint(update, "暂无离线记录.")
        return
    mixreplyprint(update, "有以下离线记录：\n" + is_connected_text, 'INFO', 'Markdown')


def setmaxthread(update: Update, context):
    if authForUser(update):
        return ConversationHandler.END
    mixreplyprint(update, "请输入你要设置的最大上传线程数.")
    return 1


def setmaxthread1(update: Update, context):
    try:
        temp_num = int(update.message.text)
    except:
        mixreplyprint(update=update, msg="输入的不是数字！", state='ERROR')
        return ConversationHandler.END
    global max_tasks_num
    max_tasks_num = temp_num
    mixreplyprint(update, '线程数成功修改，使用 /checkupload 进行查看.')
    return ConversationHandler.END


def setstate(update: Update, context):
    if authForUser(update):
        return
    global forwarding_video
    if forwarding_video:
        forwarding_video = False
        os.system("kill -9 `ps -ef| grep ffmpeg | awk '{print $2}'`")
        mixreplyprint(update, '成功关闭转发并关闭了ffmpeg拉流.')
    else:
        forwarding_video = True
        mixreplyprint(update, '成功开启转发.')


def setrtspaddr(update: Update, context):
    if authForUser(update):
        return ConversationHandler.END
    mixreplyprint(update, "发送 /add 添加设备，发送 /delete 删除设备，发送 /cancel 或其他内容取消操作.")
    return 1


def addrtspdevice1(update: Update, context):
    mixreplyprint(update, "请发送你要添加的rtsp设备地址（支持多行），添加完成后会自动重启机器人.")
    return 2


def addrtspdevice2(update: Update, context):
    if not 'rtsp://' in update.message.text:
        mixreplyprint(update, '你的输入可能不是rtsp地址，请检查其可用性，使用 /cancel 退出当前操作.')
        return 2
    file_text = open("rtsp.txt").read()
    file_text += update.message.text + '\n'
    file_text = file_text.replace('\n\n', '\n')
    open("rtsp.txt", 'w').write(file_text)
    mixreplyprint(update, "修改成功\n当前rtsp设备列表：\n" + file_text + "准备重启机器人...")
    restart_for_tg1(update, context)


def deletertspdevice1(update: Update, context):
    text_temp = '当前rtsp设备列表：\n'
    for iop in open("rtsp.txt"):
        text_temp += '`' + iop + '`'
    text_temp += "\n请发送你要删除的设备（支持多行），删除完成后会自动重启机器人."
    mixreplyprint(update, text_temp, parse_mode='Markdown')
    return 3


def deletertspdevice2(update: Update, context):
    if not 'rtsp://' in update.message.text:
        mixreplyprint(update, '你的输入可能不是rtsp地址，请检查其可用性，使用 /cancel 退出当前操作.')
        return 3
    file_text = open("rtsp.txt").read()
    file_text = file_text.replace(update.message.text, '')
    open("rtsp.txt", 'w').write(file_text)
    text_temp = '修改成功\n当前rtsp设备列表：\n'
    for iop in open("rtsp.txt"):
        text_temp += '`' + iop + '`'
    text_temp += "准备重启机器人..."
    mixreplyprint(update, text_temp, parse_mode='Markdown')
    restart_for_tg1(update, context)


def setruntime(update: Update, context):
    if authForUser(update):
        return ConversationHandler.END
    start_time_h, start_time_m = start_time
    stop_time_h, stop_time_m = stop_time
    mixreplyprint(update,
                  f'当前设置：\n`{str(start_time_h)}:{str(start_time_m)} {str(stop_time_h)}:{str(stop_time_m)}`\n请输入启动时间和停止时间\n例：`4:30 23:15`',
                  parse_mode='Markdown')
    return 1


def setruntime1(update: Update, context):
    global start_time
    global stop_time
    try:
        list_temp = update.message.text.split(' ')[0].split(':')
        start_time = (list_temp[0], list_temp[1])
        list_temp = update.message.text.split(' ')[1].split(':')
        stop_time = (list_temp[0], list_temp[1])
    except:
        mixreplyprint(update, '修改错误，请重新输入！')
        return 1
    mixreplyprint(update, '修改完成')
    return ConversationHandler.END


def cancel(update: Update, context):
    mixreplyprint(update, '您取消了操作.')
    return ConversationHandler.END


def restart_for_tg(update: Update, context):
    if authForUser(update):
        return ConversationHandler.END
    mixreplyprint(update, "你确定要重启机器人吗？\n发送 /yes 确定，发送 /cancel 或其他任意文字取消.")
    return 1


def restart_for_tg1(update: Update, context):
    mixreplyprint(update, "GCF 机器人 - 正在重启")
    for ud in all_uuid_dirs:
        try:
            shutil.rmtree(ud + f'/')
        except:
            continue
    mixreplyprint(update, "GCF 机器人 - 删除临时目录")
    os.system("kill -9 `ps -ef| grep ffmpeg | awk '{print $2}'`")
    mixreplyprint(update, "GCF 机器人 - 关闭ffmpeg")
    mixreplyprint(update, "GCF 机器人 - 重启成功")
    bot_restart_python_dir = sys.executable
    os.execl(bot_restart_python_dir, bot_restart_python_dir, *sys.argv)


def shutdown_for_tg(update: Update, context):
    if authForUser(update):
        return
    mixreplyprint(update, "你确定要关闭机器人吗？\n发送 /yes 确定，发送 /cancel 或其他任意文字取消.")
    return 1


def shutdown_for_tg1(update: Update, context):
    mixreplyprint(update, "GCF 机器人 - 正在关闭")
    for ud in all_uuid_dirs:
        try:
            shutil.rmtree(ud + f'/')
        except:
            continue
    mixreplyprint(update, "GCF 机器人 - 删除临时目录")
    os.system("kill -9 `ps -ef| grep ffmpeg | awk '{print $2}'`")
    mixreplyprint(update, "GCF 机器人 - 关闭ffmpeg")
    mixreplyprint(update, "GCF 机器人 - 关闭成功")
    os.system("kill -9 `ps -ef| grep GuanyiCameraFucker.py | awk '{print $2}'`")
    os.system("kill -9 `ps -ef| grep GuanyiCameraFucker.py | awk '{print $2}'`")


@atexit.register
def shutdown():
    mixprint("GCF 机器人 - 正在关闭")
    for ud in all_uuid_dirs:
        try:
            shutil.rmtree(ud + f'/')
        except:
            continue
    mixprint("GCF 机器人 - 删除临时目录")
    os.system("kill -9 `ps -ef| grep ffmpeg | awk '{print $2}'`")
    mixprint("GCF 机器人 - 关闭ffmpeg")
    mixprint("GCF 机器人 - 关闭成功")
    os.system("kill -9 `ps -ef| grep GuanyiCameraFucker.py | awk '{print $2}'`")
    os.system("kill -9 `ps -ef| grep GuanyiCameraFucker.py | awk '{print $2}'`")


if __name__ == '__main__':

    # 初始化全局变量
    runstatus_output = True
    is_connected = True
    forwarding_video = True
    is_connected_text = ''
    closed_connection_time = int(time.time())
    download_queue = queue.Queue(maxsize=0)
    closed_frequency = 0
    task_in_progress_num = 0
    task_in_queue_num = 0
    all_uuid_dirs = []

    try:
        open('rtsp.txt')
    except:
        logprint("请创建rtsp.txt并输入rtsp地址和设备名称!")
        exit(0)

    config_file = open('/root/GuanyiCameraFucker/config.yaml', 'r', encoding='utf-8').read()
    config = yaml.safe_load(config_file)

    tg_chat_id = config['tg_chat_id']
    tg_owner_id = config['tg_owner_id']
    tg_owner_id_list = tg_owner_id.split('|')
    tg_bot_token = config['tg_bot_token']
    proxy_url = config['proxy_url']
    max_tasks_num = int(config['max_tasks_num'])
    start_time = (config['start_time'].split(':')[0], config['start_time'].split(':')[1])
    stop_time = (config['stop_time'].split(':')[0], config['stop_time'].split(':')[1])

    if proxy_url == '':
        updater = Updater(token=tg_bot_token)
    else:
        proxy_url = proxy_url.replace('socks5', 'socks5h')
        updater = Updater(token=tg_bot_token, request_kwargs={'proxy_url': proxy_url})
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('search', search))
    dispatcher.add_handler(ConversationHandler(
        entry_points=[CommandHandler('runstatus', runstatus)],
        states={
            1: [MessageHandler(Filters.text, runstatus1)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    ))
    dispatcher.add_handler(CommandHandler('isonline', isonline))
    dispatcher.add_handler(CommandHandler('offlinetext', offlinetext))
    dispatcher.add_handler(ConversationHandler(
        entry_points=[CommandHandler('setmaxthread', setmaxthread)],
        states={
            1: [CommandHandler('cancel', cancel), MessageHandler(Filters.text, setmaxthread1)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    ))
    dispatcher.add_handler(CommandHandler('setstate', setstate))
    dispatcher.add_handler(ConversationHandler(
        entry_points=[CommandHandler('setrtspaddr', setrtspaddr)],
        states={
            1: [CommandHandler('add', addrtspdevice1), CommandHandler('delete', deletertspdevice1),
                CommandHandler('cancel', cancel), MessageHandler(Filters.text, cancel)],
            2: [CommandHandler('cancel', cancel), MessageHandler(Filters.text, addrtspdevice2)],
            3: [CommandHandler('cancel', cancel), MessageHandler(Filters.text, deletertspdevice2)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    ))
    dispatcher.add_handler(ConversationHandler(
        entry_points=[CommandHandler('setruntime', setruntime)],
        states={
            1: [CommandHandler('cancel', cancel), MessageHandler(Filters.text, setruntime1)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    ))
    dispatcher.add_handler(ConversationHandler(
        entry_points=[CommandHandler('restart', restart_for_tg)],
        states={
            1: [CommandHandler('yes', restart_for_tg1), CommandHandler('cancel', cancel),
                MessageHandler(Filters.text, cancel)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    ))
    dispatcher.add_handler(ConversationHandler(
        entry_points=[CommandHandler('shutdown', shutdown_for_tg)],
        states={
            1: [CommandHandler('yes', shutdown_for_tg1), CommandHandler('cancel', cancel),
                MessageHandler(Filters.text, cancel)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    ))
    dispatcher.add_handler(CommandHandler('help', helpness))

    if proxy_url != '':
        proxy = telegram.utils.request.Request(proxy_url=proxy_url)
        bot = Bot(token=tg_bot_token, request=proxy)
    else:
        bot = Bot(token=tg_bot_token)

    # 提交命令
    commands = [
        ("start", "开始"),
        ("search", "搜索历史回放"),
        ("isonline", "查看当前在线状态"),
        ("runstatus", "查看当前运行状态"),
        ("offlinetext", "查看掉线记录"),
        ("setstate", "切换视频转发状态"),
        ("setmaxthread", "设置最大上传线程数"),
        ("setruntime", "设置运行时段"),
        ("setrtspaddr", "配置rtsp设备地址"),
        ("restart", "重启 GCF"),
        ("shutdown", "关闭 GCF"),
        ("help", "帮助列表"),
        ("cancel", "取消当前操作"),
    ]
    bot.set_my_commands(commands)

    i = 0
    run_devices = []
    threading.Thread(name="check_time_to_run_code", target=check_time_to_run_code).start()
    threading.Thread(name="queue_to_upload_video", target=queue_to_upload_video).start()
    for li in open('rtsp.txt'):
        if li == '':
            continue
        i += 1
        rtsp_addr = li.replace('\n', '')
        uuid_name = str(uuid.uuid4())
        uuid_dir = os.getcwd() + "/" + uuid_name
        all_uuid_dirs.append(uuid_dir)
        if os.path.exists(uuid_dir):
            shutil.rmtree(uuid_dir + f'/')
        os.makedirs(uuid_dir)
        os.makedirs(uuid_dir + "/temp")
        run_devices.append(rtsp_addr[rtsp_addr.find('@127.0.0.1:') + 11:].replace('/', 'G'))  # 加入设备列表
        threading.Thread(name=uuid_name + "-check_file", target=check_file_exist, args=(rtsp_addr, uuid_name)).start()
        threading.Thread(name=uuid_name + "-ffmpeg_download", target=ffmpeg_download_video,
                         args=(rtsp_addr, uuid_dir)).start()
    mixprint("GCF 机器人 - 开始运行")
    updater.start_polling()
    updater.idle()
