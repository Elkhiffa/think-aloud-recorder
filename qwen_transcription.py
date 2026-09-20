"""Qwen recorded-audio REST client. Never upload the recording or mixed game track."""
import json
import math
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from hotword_files import split_words, validate_words

MODEL = 'qwen-audio-3.0-asr-flash-filetrans'
API_BASE = 'https://dashscope.aliyuncs.com/api/v1'
REGISTER_URL = 'https://account.aliyun.com/register/register.htm'
BILLING_URL = 'https://billing-cost.console.aliyun.com/'
CONSOLE_URL = 'https://bailian.console.aliyun.com/?tab=model'


class QwenError(RuntimeError):
    def __init__(self, message, code=''):
        super().__init__(message)
        self.code = code


# Translate provider error codes, never echo arbitrary response messages or signed URLs.
# Reference: https://help.aliyun.com/zh/model-studio/error-code
FAILURE_HINTS = {
    'ASR_RESPONSE_HAVE_NO_WORDS': '未识别到可转写的语音。请检查麦克风是否静音、是否选对设备，并确认口述录音中有清晰的人声。',
    'SUCCESS_WITH_NO_VALID_FRAGMENT': '未检测到有效语音。请检查麦克风是否静音、是否选对设备，并确认口述录音中有清晰的人声。',
    'FILE_DOWNLOAD_FAILED': 'Qwen 未能下载口述录音。请稍后重试；若持续失败，请检查上传服务。',
    'FILE_404_NOT_FOUND': 'Qwen 找不到上传的口述录音，文件可能已过期。请重试以重新上传。',
    'FILE_403_FORBIDDEN': 'Qwen 没有权限读取上传的口述录音。请重试以重新获取上传权限。',
    'FILE_CHECK_FAILED': '平台未通过音频格式检查。请检查口述录音能否正常播放，或改用离线转写。',
    'FILE_PARSE_FAILED': '平台无法解析口述录音。请检查录音能否正常播放，或改用离线转写。',
    'FILE_NORMALIZE_FAILED': '平台无法处理口述录音。请检查录音是否损坏，或改用离线转写。',
    'DECODE_ERROR': '平台无法解码口述录音。请检查录音能否正常播放，或改用离线转写。',
    'NO_VALID_AUDIO_ERROR': '平台认为口述音频无效。请检查录音能否正常播放，或改用离线转写。',
    'FILE_TOO_LARGE': '口述录音超过平台的文件大小限制。请缩短单次录制，或改用离线转写。',
    'AUDIO_DURATION_TOO_LONG': '口述录音超过平台的时长限制。请缩短单次录制，或改用离线转写。',
    'FILE_TRANS_TASK_EXPIRED': '云端任务已过期。请重试以重新提交录音。',
    'FILE_SERVER_ERROR': '平台暂时无法访问录音所在的服务。请稍后重试。',
    'AllocationQuota.FreeTierOnly': '模型免费额度已用尽，平台限制了继续调用。请在百炼检查“免费额度用完即停”、账号认证和余额；充值后也需确认该开关。',
    'Arrearage': 'API Key 所属账号存在欠费或余额异常。请检查该账号的账单和余额；刚充值可稍后重试。',
}


def _error_code(payload):
    if not isinstance(payload, dict):
        return ''
    value = payload.get('code', '')
    if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', value):
        return value
    # Some task responses put only the symbolic code in message.
    message = payload.get('message')
    return message if isinstance(message, str) and message in FAILURE_HINTS else ''


def _failure_hint(code, http_status=None):
    if code in FAILURE_HINTS:
        return FAILURE_HINTS[code]
    lower = code.lower()
    if http_status == 401 or 'apikey' in lower or lower in ('invalid_api_key', 'invalidapikey'):
        return 'API Key 无效或已失效。请在“转写服务”中检查并重新填写北京地域的百炼 API Key。'
    if http_status == 429 or 'throttling' in lower or lower in ('limitrequests', 'limit_requests', 'resourceexhausted'):
        return '调用过于频繁或超过并发限制。请稍后重试。'
    if http_status == 402 or any(s in lower for s in ('balance', 'arrearage', 'quota', 'payment', 'billoverdue')):
        return '账号额度或计费状态受限。请在百炼检查该模型的额度、余额及服务状态。'
    if http_status == 403 or 'accessdenied' in lower or 'access_denied' in lower:
        return '没有调用权限。请检查百炼服务是否开通，以及密钥的地域和模型权限。'
    if (http_status is not None and http_status >= 500) or lower in ('internalerror', 'internal_error', 'serviceunavailable'):
        return '云端服务暂时异常。请稍后重试。'
    return ''


def _task_error(status, output, data, *, subtask=False):
    results = output.get('results', [])
    failed = [r for r in results if isinstance(r, dict) and r.get('subtask_status') != 'SUCCEEDED'] if isinstance(results, list) else []
    code = next((code for source in (*failed, output, data) if (code := _error_code(source))), '')
    hint = _failure_hint(code)
    if not hint:
        if status == 'CANCELED':
            hint = '云端任务已取消，可重试提交。'
        elif status == 'UNKNOWN':
            hint = '云端任务已过期或无法查询，请检查百炼任务记录后重试。'
        else:
            hint = ('暂时无法解释平台返回的错误码' if code else '平台未提供具体失败原因') + '，请在百炼任务记录中查看详情。'
    title = '口述音轨转写子任务失败' if subtask else 'Qwen 转写未完成'
    message = title + '：' + hint + '\n原录音与任务记录已保留。'
    if code:
        message += '\n平台错误码：' + code
    return QwenError(message, code)


def _official_oss_url(url):
    parsed = urlsplit(url)
    host = parsed.hostname or ''
    if (parsed.scheme != 'https' or parsed.username or parsed.password
            or parsed.port not in (None, 443)
            or not re.fullmatch(r'[a-z0-9-]+\.oss-[a-z0-9-]+\.aliyuncs\.com', host)):
        raise QwenError('平台返回了无法验证的文件地址，已停止传输。')
    return url


def _data(response):
    try:
        value = response.json()
    except (ValueError, UnicodeError):
        raise QwenError('平台返回的内容不是有效 JSON。') from None
    if not isinstance(value, dict):
        raise QwenError('平台返回的数据格式不正确。')
    return value


def _error(response, stage):
    try:
        code = _error_code(response.json())
    except ValueError:
        code = ''
    hint = _failure_hint(code, response.status_code)
    return QwenError(f'{stage}失败（HTTP {response.status_code}' + (f' / {code}' if code else '') + '）。' + hint, code)


def _get(client, url, *, headers=None, params=None, sleep=time.sleep):
    for attempt in range(3):
        try:
            response = client.get(url, headers=headers, params=params)
        except httpx.TransportError:
            if attempt == 2:
                raise QwenError('网络连接中断。已有任务编号会保留，点击重试可继续查询。') from None
        else:
            if response.status_code < 400 or (response.status_code < 500 and response.status_code != 429):
                return response
            if attempt == 2:
                return response
        sleep(attempt + 1)


def _policy(client, key, options, sleep=time.sleep):
    if options.get('region', 'beijing') != 'beijing' or options.get('model') != MODEL:
        raise QwenError('当前配置需要北京地域的 Qwen 录音文件转写模型。')
    response = _get(client, API_BASE + '/uploads',
                    headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
                    params={'action': 'getPolicy', 'model': options['model']}, sleep=sleep)
    if response.status_code != 200:
        raise _error(response, '检查上传权限')
    policy = _data(response).get('data')
    required = ('upload_host', 'upload_dir', 'oss_access_key_id', 'signature', 'policy',
                'x_oss_object_acl', 'x_oss_forbid_overwrite')
    if not isinstance(policy, dict) or any(not policy.get(field) for field in required):
        raise QwenError('平台返回的上传凭证不完整。')
    _official_oss_url(policy['upload_host'])
    if policy['x_oss_object_acl'] != 'private':
        raise QwenError('临时上传空间没有返回私有访问权限，已停止上传。')
    return policy


def check_connection(key, options, client=None):
    if not key:
        raise QwenError('请先在“转写服务”中填写 API Key。')
    if client is None:
        with httpx.Client(timeout=30, follow_redirects=False) as owned:
            return check_connection(key, options, owned)
    _policy(client, key, options)
    return '认证及临时上传权限正常。未上传录音，尚未验证实际转写。'


def _upload(client, key, options, audio, progress, sleep):
    policy = _policy(client, key, options, sleep)
    size_limit = min(1024 ** 3, int(float(policy.get('max_file_size_mb', 1024)) * 1024 ** 2))
    if audio.stat().st_size > size_limit:
        raise QwenError('独立口述音轨超过当前临时上传额度，请缩短单次录制或使用离线转写。原录音已保留。')
    filename = uuid.uuid4().hex + '.flac'
    object_key = policy['upload_dir'].rstrip('/') + '/' + filename
    form = {'OSSAccessKeyId': policy['oss_access_key_id'], 'Signature': policy['signature'],
            'policy': policy['policy'], 'x-oss-object-acl': 'private',
            'x-oss-forbid-overwrite': policy['x_oss_forbid_overwrite'],
            'key': object_key, 'success_action_status': '200'}
    progress(f'上传独立口述音轨（{audio.stat().st_size / 1024 ** 2:.1f} MB）…')
    try:
        with audio.open('rb') as source:
            # A file handle streams long audio; no bearer credential is sent to OSS.
            response = client.post(policy['upload_host'], data=form,
                                   files={'file': (filename, source, 'audio/flac')}, timeout=600)
    except httpx.TransportError:
        raise QwenError('口述音轨上传中断，尚未提交转写任务。可以重试。') from None
    if response.status_code != 200:
        raise _error(response, '上传独立口述音轨')
    return 'oss://' + object_key


def normalize_result(raw, duration):
    """Keep provider text verbatim and convert real millisecond word times to seconds."""
    transcripts = raw.get('transcripts')
    if not isinstance(transcripts, list):
        raise QwenError('转写结果缺少 transcripts，原始返回已保留。')
    properties = raw.get('properties', {})
    source_ms = properties.get('original_duration_in_milliseconds')
    if source_ms is not None and abs(float(source_ms) / 1000 - duration) > 1:
        raise QwenError('平台识别的录音长度与本场次不符，已停止生成错位字幕。')
    result = []
    for transcript in transcripts:
        if transcript.get('channel_id') != 0:
            raise QwenError('转写结果不是独立口述音轨。')
        sentences = transcript.get('sentences')
        if not isinstance(sentences, list) or (transcript.get('text', '').strip() and not sentences):
            raise QwenError('平台没有返回句级时间戳。')
        for sentence in sentences:
            text = sentence.get('text', '')
            if not isinstance(text, str):
                raise QwenError('平台返回的句子格式不正确。')
            if not text.strip():
                continue
            start, end = _times(sentence, duration)
            words = []
            for word in sentence.get('words', []):
                ws, we = _times(word, duration)
                token = word.get('text', '') + word.get('punctuation', '')
                if ws < start - .05 or we > end + .05 or (words and ws < words[-1]['start']):
                    raise QwenError('平台返回的词级时间戳错位，原始返回已保留。')
                if token:
                    words.append({'start': ws, 'end': we, 'word': token})
            if not words:
                raise QwenError('平台没有返回词级时间戳，无法生成逐词同步回看。')
            if result and start < result[-1]['start']:
                raise QwenError('平台返回的句子时间顺序不正确。')
            result.append({'start': start, 'end': end, 'text': text, 'words': words})
    return result


def _times(item, duration):
    try:
        start, end = float(item['begin_time']) / 1000, float(item['end_time']) / 1000
    except (TypeError, ValueError, KeyError):
        raise QwenError('平台返回的时间戳不完整。') from None
    if not (math.isfinite(start) and math.isfinite(end) and 0 <= start <= end <= duration + .05):
        raise QwenError('平台返回的时间戳超出录音范围。')
    return round(min(start, duration), 3), round(min(end, duration), 3)


def _raw_without_urls(raw):
    # The recognition payload is untouched; only temporary download locators are omitted.
    return {key: value for key, value in raw.items() if key not in ('file_url', 'transcription_url')}


def transcribe(audio, cache, options, duration, progress, key, *, client=None,
               sleep=time.sleep, max_wait=4 * 3600):
    from recorder import read, write
    audio, cache = Path(audio), Path(cache)
    if audio.name != '口述.flac':
        raise QwenError('云端转写只接受整理流程提取的独立口述音轨。')
    if not 0 < duration <= 12 * 3600 or audio.stat().st_size > 1024 ** 3:
        raise QwenError('云端单次录音须在 12 小时、1 GB 以内。原录音已保留，可使用离线转写。')
    cache.mkdir(parents=True, exist_ok=True)
    raw_path, job_path = cache / '云端原始结果.json', cache / '云端任务.json'
    if raw_path.exists():
        progress('读取已保存的 Qwen 转写结果…')
        return normalize_result(read(raw_path), duration)
    if not key:
        raise QwenError('尚未填写北京地域的百炼 API Key。请打开“转写服务”完成配置，再重试本场次。')
    try:
        terms = validate_words(split_words(options.get('hotwords', '')))
    except ValueError as error:
        raise QwenError(str(error)) from error
    if client is None:
        with httpx.Client(timeout=60, follow_redirects=False) as owned:
            return transcribe(audio, cache, options, duration, progress, key,
                              client=owned, sleep=sleep, max_wait=max_wait)
    job = read(job_path) if job_path.exists() else {}
    if job.get('state') == 'SUBMITTING' and not job.get('task_id'):
        raise QwenError('上次提交结果不确定，已暂停以免重复计费。请在百炼任务记录核对任务编号，再用“云任务恢复”继续。')
    headers = {'Authorization': 'Bearer ' + key}
    if not job.get('task_id') or job.get('state') in ('FAILED', 'CANCELED', 'UNKNOWN', 'REJECTED'):
        if job:
            write(cache / ('任务记录-' + uuid.uuid4().hex[:10] + '.json'), job)
        oss_url = _upload(client, key, options, audio, progress, sleep)
        parameters = {'channel_id': [0], 'diarization_enabled': False,
                      'special_word_filter': {'system_reserved_filter': False}}
        if options.get('language'):
            parameters['language_hints'] = [options['language']]
        if terms:
            parameters['vocabulary'] = {term: 2 for term in terms}
        # Persist intent BEFORE a potentially billable POST. Unknown outcomes never auto-resubmit.
        job = {'state': 'SUBMITTING', 'submitted_at': time.time(), 'model': options['model']}
        write(job_path, job)
        progress('向 Qwen 提交录音转写任务…')
        try:
            response = client.post(API_BASE + '/services/audio/asr/transcription',
                                   headers={**headers, 'X-DashScope-Async': 'enable',
                                            'X-DashScope-OssResourceResolve': 'enable'},
                                   json={'model': options['model'], 'input': {'file_urls': [oss_url]},
                                         'parameters': parameters})
        except httpx.TransportError:
            raise QwenError('提交时连接中断，结果不确定。请在百炼核对任务记录；应用不会自动重复提交计费。') from None
        if response.status_code not in (200, 202):
            if 400 <= response.status_code < 500 and response.status_code != 408:
                job['state'] = 'REJECTED'
                write(job_path, job)
            raise _error(response, '提交转写任务')
        output = _data(response).get('output', {})
        task_id = output.get('task_id')
        if not isinstance(task_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', task_id):
            raise QwenError('提交后未收到任务编号，请先在百炼核对任务记录。')
        job.update(task_id=task_id, state=output.get('task_status', 'PENDING'))
        write(job_path, job)
    started, last_progress = time.monotonic(), -100
    while True:
        response = _get(client, API_BASE + '/tasks/' + job['task_id'], headers=headers, sleep=sleep)
        if response.status_code == 404:
            job['state'] = 'UNKNOWN'
            write(job_path, job)
            raise QwenError('云端任务已过期或无法查询。原录音已保留；再次重试会提交新任务。')
        if response.status_code != 200:
            raise _error(response, '查询转写任务（编号已保存）')
        data = _data(response)
        output = data.get('output', {})
        status = output.get('task_status')
        if status not in ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELED', 'UNKNOWN'):
            raise QwenError('平台返回的任务状态无法识别，任务编号已保留。')
        job.update(state=status, checked_at=time.time())
        if 'usage' in data:
            job['usage'] = data['usage']
        write(job_path, job)
        if status == 'SUCCEEDED':
            results = output.get('results', [])
            if len(results) != 1 or results[0].get('subtask_status') != 'SUCCEEDED':
                error = _task_error('FAILED', output, data, subtask=True)
                job.update(state='FAILED', error_code=error.code, error=str(error))
                write(job_path, job)
                raise error
            url = _official_oss_url(results[0].get('transcription_url', ''))
            downloaded = _get(client, url, sleep=sleep)
            if downloaded.status_code != 200:
                raise _error(downloaded, '下载转写结果（任务编号已保存）')
            raw = _data(downloaded)
            write(raw_path, _raw_without_urls(raw))
            return normalize_result(raw, duration)
        if status in ('FAILED', 'CANCELED', 'UNKNOWN'):
            error = _task_error(status, output, data)
            job.update(error_code=error.code, error=str(error))
            write(job_path, job)
            raise error
        elapsed = time.monotonic() - started
        if elapsed - last_progress >= 15:
            progress(('Qwen 正在排队' if status == 'PENDING' else 'Qwen 正在转写') + f'，已等待 {int(elapsed)} 秒…')
            last_progress = elapsed
        if elapsed >= max_wait:
            raise QwenError('等待时间较长，任务编号已保留。稍后重试会继续查询同一任务。')
        sleep(3)


def restore_task(cache, task_id):
    """User-supplied ID resolves an uncertain submission without charging another request."""
    from recorder import read, write
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', task_id):
        raise QwenError('任务编号格式不正确。')
    path = Path(cache) / '云端任务.json'
    job = read(path) if path.exists() else {}
    job.update(task_id=task_id, state='PENDING', restored_at=time.time())
    write(path, job)
