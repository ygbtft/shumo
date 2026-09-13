"""两种官方运行入口共用的日志格式，不负责策略选择或 HTTP 通信。"""
from datetime import datetime
import json
import time


def write_json(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2)
    path.write_text(text + '\n', encoding='utf8')


def create_output(parent, case_code):
    # 每局单独保存；微秒时间戳避免覆盖已有实验输出。
    name = datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '-' + case_code
    folder = parent / name
    folder.mkdir(parents=True)
    return folder


class RequestLog:
    def __init__(self, path):
        self.path = path
        self.count = 0
        self.enter_ms = None
        self.exit_ms = None

    def append(self, row):
        with self.path.open('a', encoding='utf8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')

        # 原客户端的传输失败记录没有 response 字段，属于单独的日志事件。
        if row.get('event') == 'transport_failure':
            return
        self.count += 1
        if not row['response']['accepted']:
            return
        if row['path'] == '/enter':
            self.enter_ms = row['response']['real_timestamp_ms']
        elif row['path'] == '/exit':
            self.exit_ms = row['response']['real_timestamp_ms']

    def summary(self, policy, client, started, completed):
        cleared = len(policy.cleared)
        average_time = None
        if cleared:
            average_time = client.virtual_s / cleared

        # 未正常退出的记录没有完整程序时间，不能填成 0 秒。
        program_time = None
        if self.enter_ms is not None and self.exit_ms is not None:
            program_time = (self.exit_ms - self.enter_ms) / 1000

        return {
            'status': 'completed' if completed else 'interrupted',
            'cleared': cleared,
            'total_virtual_s': client.virtual_s,
            'average_localization_clear_s': average_time,
            'program_runtime_s': program_time,
            'client_policy_wall_s': time.perf_counter() - started,
            'official_calls': self.count,
            'mock_executions': 0,
        }
