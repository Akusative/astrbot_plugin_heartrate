import os
import sys
import json
import time
import shutil
import subprocess
import asyncio
from datetime import datetime

from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.core.provider.entities import ProviderRequest


# 心率数据文件 - 自动查找
HEARTRATE_FILE = ''
SERVICE_DIR = ''


def _auto_find_heartrate_file():
    candidates = [
        os.path.abspath(os.path.join('data', 'heartrate_server', 'heartrate_latest.json')),
        os.path.abspath(os.path.join('data', 'heartrate_latest.json')),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c, os.path.dirname(c)
    return candidates[0], os.path.dirname(candidates[0])


def _read_heartrate():
    try:
        if not HEARTRATE_FILE or not os.path.exists(HEARTRATE_FILE):
            return None
        with open(HEARTRATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error('读取心率数据失败: ' + str(e))
        return None


def _analyze_trend(history):
    if not history or len(history) < 3:
        return None
    recent = [h['bpm'] for h in history[-10:]]
    avg = sum(recent) / len(recent)
    last3 = recent[-3:]
    if last3[-1] > last3[0] + 5:
        trend = '上升中'
    elif last3[-1] < last3[0] - 5:
        trend = '下降中'
    else:
        trend = '平稳'
    current = recent[-1]
    if current < 60:
        zone = '静息'
    elif current < 80:
        zone = '放松'
    elif current < 100:
        zone = '轻度兴奋'
    elif current < 120:
        zone = '中度兴奋'
    elif current < 140:
        zone = '高度兴奋'
    elif current < 160:
        zone = '剧烈'
    else:
        zone = '极限'
    return {'trend': trend, 'zone': zone, 'avg': round(avg, 1),
            'max': max(recent), 'min': min(recent)}


def _format_time_ago(ts):
    if not ts:
        return '未知'
    diff = time.time() - ts
    if diff < 10:
        return '刚刚'
    elif diff < 60:
        return str(int(diff)) + '秒前'
    elif diff < 3600:
        return str(int(diff // 60)) + '分钟前'
    elif diff < 86400:
        return str(int(diff // 3600)) + '小时前'
    else:
        return str(int(diff // 86400)) + '天前'


@register('astrbot_plugin_heartrate', '沈菀', '心跳感应 - 实时心率监测', 'v1.3.1')
class HeartRatePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        global HEARTRATE_FILE, SERVICE_DIR
        HEARTRATE_FILE, SERVICE_DIR = _auto_find_heartrate_file()
        
        # 初始化服务目录
        if not os.path.exists(SERVICE_DIR):
            try:
                os.makedirs(SERVICE_DIR, exist_ok=True)
                logger.info(f"已创建心率服务目录: {SERVICE_DIR}")
            except Exception as e:
                logger.error(f"创建心率服务目录失败: {e}")
                
        # 自动释放脚本
        source_script = os.path.join(os.path.dirname(__file__), 'heartrate_receiver_v2.py')
        target_script = os.path.join(SERVICE_DIR, 'heartrate_receiver_v2.py')
        
        if os.path.exists(source_script) and not os.path.exists(target_script):
            try:
                shutil.copy2(source_script, target_script)
                logger.info(f"已释放心率服务脚本到: {target_script}")
            except Exception as e:
                logger.error(f"释放服务脚本失败: {e}")
                
        logger.info('心跳感应插件已加载 | 数据路径: ' + HEARTRATE_FILE)
        
        # 随插件自然启动拉起心率服务端口
        asyncio.create_task(self._start_service_bg())

    async def _start_service_bg(self):
        """后台启动服务"""
        is_running = await self._start_service()
        if is_running:
            logger.info("心率接收服务已成功在后台自启动 (端口 3476)")
        else:
            logger.error("心率接收服务后台自启动失败")

    async def _start_service(self):
        try:
            # 兼容无窗口进程：在 Windows 上通过 wmic 杀掉心率服务
            if sys.platform == 'win32':
                subprocess.run('wmic process where "commandline like \'%heartrate_receiver_v2.py%\' and name=\'python.exe\'" call terminate', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.run(['pkill', '-f', 'heartrate_receiver_v2.py'],
                               timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            await asyncio.sleep(1)
            
            if SERVICE_DIR and os.path.exists(os.path.join(SERVICE_DIR, 'heartrate_receiver_v2.py')):
                if sys.platform == 'win32':
                    subprocess.Popen(
                        ['python', 'heartrate_receiver_v2.py'],
                        cwd=SERVICE_DIR,
                        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
                    )
                else:
                    subprocess.Popen(
                        ['python3', 'heartrate_receiver_v2.py'],
                        cwd=SERVICE_DIR,
                        start_new_session=True
                    )
                await asyncio.sleep(3)
                
                if sys.platform == 'win32':
                    check = subprocess.run('netstat -ano | findstr 3476', shell=True, capture_output=True, text=True, timeout=5)
                    is_running = 'LISTENING' in check.stdout
                else:
                    check = subprocess.run('ss -tuln | grep 3476', shell=True, capture_output=True, text=True, timeout=5)
                    is_running = check.stdout.strip() != ""
                
                return is_running
            return False
        except Exception as e:
            logger.error('服务启动异常: ' + str(e))
            return False

    @filter.command('查看心率')
    async def check_heartrate_cmd(self, event: AstrMessageEvent):
        try:
            data = _read_heartrate()
            if not data:
                yield event.plain_result('心率服务未运行或无数据，请发送 /重启心率服务')
                return
            bpm = data.get('bpm', 0)
            session_active = data.get('session_active', False)
            ts = data.get('timestamp', 0)
            history = data.get('recent_history', [])
            if not session_active or bpm == 0:
                yield event.plain_result('心率监测未开启，请在手表上开启运动模式')
                return
            is_stale = (time.time() - ts) > 60 if ts else True
            if is_stale:
                yield event.plain_result('心率数据已过期，请检查手表连接')
                return
            time_ago = _format_time_ago(ts)
            analysis = _analyze_trend(history)
            lines = []
            lines.append('\u2764\ufe0f 实时心率: ' + str(bpm) + ' BPM（' + time_ago + '）')
            if analysis:
                lines.append('趋势: ' + analysis['trend'] + ' | 状态: ' + analysis['zone'])
                lines.append('近期范围: ' + str(analysis['min']) + '-' + str(analysis['max']) + ' BPM')
            if history:
                recent = history[-5:]
                hr_seq = ' > '.join([str(h['bpm']) for h in recent])
                lines.append('最近: ' + hr_seq)
            lines.append('总记录: ' + str(data.get('history_count', 0)) + '条')
            yield event.plain_result('\n'.join(lines))
        except Exception as e:
            logger.error('查看心率指令异常: ' + str(e))
            yield event.plain_result('获取心率失败，发生内部错误')

    @filter.command('重启心率服务')
    async def restart_heartrate_service(self, event: AstrMessageEvent):
        yield event.plain_result('正在启动/重启心率服务，请稍候...')
        is_running = await self._start_service()
        if is_running:
            yield event.plain_result('心率服务启动/重启成功，请在手表上重新开启运动模式')
        else:
            yield event.plain_result('心率服务启动失败，请检查服务器或系统日志')

    @filter.on_llm_request(priority=8)
    async def inject_heartrate(self, event: AstrMessageEvent, req: ProviderRequest):
        try:
            data = _read_heartrate()
            if not data:
                return
            bpm = data.get('bpm', 0)
            session_active = data.get('session_active', False)
            ts = data.get('timestamp', 0)
            history = data.get('recent_history', [])
            is_stale = (time.time() - ts) > 300 if ts else True
            if not session_active or bpm == 0 or is_stale:
                return
            time_ago = _format_time_ago(ts)
            parts = ['实时心率: ' + str(bpm) + ' BPM (更新于' + time_ago + ')']
            analysis = _analyze_trend(history)
            if analysis:
                parts.append('趋势: ' + analysis['trend'])
                parts.append('状态: ' + analysis['zone'])
                parts.append('近期范围: ' + str(analysis['min']) + '-' + str(analysis['max']) + ' BPM')
            if history and len(history) >= 3:
                hr_seq = ', '.join([str(h['bpm']) for h in history[-5:]])
                parts.append('最近心率序列: ' + hr_seq)
            hr_prompt = ' | '.join(parts)
            
            prompt_injection = f'\n\n[用户心率数据] {hr_prompt}'
            if req.system_prompt:
                if '[用户心率数据]' not in req.system_prompt:
                    req.system_prompt += prompt_injection
            else:
                req.system_prompt = f'[用户心率数据] {hr_prompt}'
            logger.info('已添加心跳感知信息: ' + hr_prompt)
        except Exception as e:
            logger.error('心率注入异常: ' + str(e))

    @filter.llm_tool(name='get_heartrate')
    async def get_heartrate(self, event: AstrMessageEvent, detail: bool = False) -> str:
        '''获取用户的实时心率数据。当你想知道用户当前的心跳、身体状态、情绪变化时调用此工具。在亲密互动、运动、聊天中随时可以调用来感知用户的生理状态。
        Args:
            detail(boolean): 是否返回详细信息（包含趋势分析和历史记录），默认false
        '''
        try:
            data = _read_heartrate()
            if data is None:
                return '心率服务未运行'
            bpm = data.get('bpm', 0)
            session_active = data.get('session_active', False)
            ts = data.get('timestamp', 0)
            history = data.get('recent_history', [])
            if not session_active or bpm == 0:
                return '用户当前未开启心率监测，无法获取实时心率'
            time_ago = _format_time_ago(ts)
            is_stale = (time.time() - ts) > 30 if ts else True
            if detail:
                analysis = _analyze_trend(history)
                if analysis:
                    trend_info = '趋势: ' + analysis['trend'] + ' | 状态: ' + analysis['zone'] + ' | 均值: ' + str(analysis['avg']) + ' BPM | 范围: ' + str(analysis['min']) + '-' + str(analysis['max']) + ' BPM'
                else:
                    trend_info = '数据不足'
                recent_str = ''
                if history:
                    recent_str = ' | 最近: ' + ', '.join([str(h['bpm']) for h in history[-5:]])
                return '实时心率: ' + str(bpm) + ' BPM (' + time_ago + ') | ' + ('实时' if not is_stale else '延迟') + ' | ' + trend_info + recent_str + ' | 总记录: ' + str(data.get('history_count', 0))
            else:
                result = '实时心率: ' + str(bpm) + ' BPM (' + time_ago + ')'
                analysis = _analyze_trend(history)
                if analysis:
                    result += ' | ' + analysis['trend'] + ' | ' + analysis['zone']
                return result
        except Exception as e:
            logger.error('get_heartrate工具异常: ' + str(e))
            return '获取心率数据时发生内部错误'
