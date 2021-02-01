import datetime
import json
import logging
from logging.config import fileConfig
import re

import requests
from flask_apscheduler import APScheduler
from flask import Flask, jsonify

app = Flask(__name__)

fileConfig('logging.cfg')
logger = logging.getLogger('root')

# MODE = 'prod' || 'dev'
MODE = 'dev'
with open(f'config_{MODE}.json', 'r') as f:
    config = json.load(f)

git_cfg = config['github']
slack_cfg = config['slack']
checker_cfg = config['checker']

SLACK_API_URL = 'https://slack.com/api/chat.postMessage'
GIT_API_URL = f'https://api.github.com/repos/{git_cfg["repo"]["owner"]}/{git_cfg["repo"]["name"]}/commits'


class Config(object):
    job_func = config['job']['func']
    schedule = config['job']['schedule']
    JOBS = [
        {
            'id': f'{MODE}_job01',
            'func': f'{job_func["file"]}:{job_func["name"]}',
            'args': job_func["args"],
            'trigger': 'cron',
            'day_of_week': schedule['day_of_week'],
            'hour': schedule['hour'],
            'minute': schedule['minute'],
            'end_date': schedule['end_date'],
        }
    ]

    SCHEDULER_EXECUTORS = {
        'default': {'type': 'threadpool', 'max_workers': 1},
    }

    SCHEDULER_JOB_DEFAULTS = {
        'coalesce': False,
        'max_instances': 1,
    }

    SCHEDULER_API_ENABLED = True


# TODO : test 분리
def test():
    send_msg_less_committer(n_days=checker_cfg['period_day'], author_infos=checker_cfg['whom'],
                           keyword=checker_cfg['commit_keyword'])
    return 'working'


def send_msg_less_committer(keyword, n_days=1, author_infos=[{"committer": git_cfg['user'], "target_commit_count": 1}]):
    """현재부터 24* n 시간 전(n일 전)까지의 특정 commit 수가 n개 미만이면, 해당 사용자에게 멘션을 걸어 슬랙 알람 메시지를 전송합니다.

        Keyword arguments:
        n_days -- 지금으로부터 n 일 전 (기본값 1)
        author_info -- commit 수를 체크할 committer 와 committer 별 목표 commit 수
                    e.g. {"committer": "repo-committer-user-name", "target_commit_count": 1}
        keyword --  regexp. 이 Regexp를 만족하는(포함하는) commit message 만 count 함.
    """
    before_date = (datetime.datetime.now() - datetime.timedelta(days=n_days)).astimezone().isoformat()
    commit_cnt = count_repo_commit(checked_date=before_date, author_infos=author_infos, keyword=keyword)

    for info in author_infos:
        author = info['committer']
        target_commit_cnt = info['target_commit_count']
        if commit_cnt[author] < target_commit_cnt:
            msg = slack_cfg['msg']['format'].format(*slack_cfg['msg']['args'])
            send_slack_mention_msg(author, appended_msg=msg)


def count_repo_commit(checked_date, keyword, author_infos=[{"committer": git_cfg['user'], "target_commit_count": 1}]):
    """현재부터 checked_date 후로 발생한 특정 repo commit 중,
    특정 키워드가 포함된 commit 수를 committer 별(config.json에 입력된 committer)로 반환합니다.

            Keyword arguments:
            checked_date -- timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.
            author_info -- commit 수를 체크할 committer 와 committer 별 목표 commit 수
                    e.g. {"committer": "repo-committer-user-name", "target_commit_count": 1}
            keyword --  regexp. 이 Regexp를 만족하는(포함하는) commit message 만 count 함.
    """

    result = {}

    for info in author_infos:
        author = info['committer']
        result[author] = count_repo_commit_per_author(checked_date=checked_date, author=author, keyword_regexp=keyword)

    return result


def count_repo_commit_per_author(checked_date, author, keyword_regexp=''):
    """현재부터 checked_date 후로 발생한 특정 repo 의 author 의 commit 중,
    특정 키워드가 포함된 commit 수를 반환합니다.

            Keyword arguments:
            checked_date -- timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.
            author_info -- commit 수를 체크할 committer 와 committer 별 목표 commit 수
                    e.g. {"committer": "repo-committer-user-name", "target_commit_count": 1}
            keyword_regexp --  regexp. 이 Regexp를 만족하는(포함하는) commit message 만 count 함.
    """

    cnt = 0

    param = {'author': author, 'since': checked_date}
    r = requests.get(GIT_API_URL, params=param, auth=(git_cfg['user'], git_cfg['token']))

    if r.status_code == 200:
        commit_list = r.json()

        if keyword_regexp == '':
            cnt = len(commit_list)
            return cnt

        for commit in commit_list:
            msg = commit['commit']['message']
            if re.search(keyword_regexp, msg) is not None:
                # print(msg)
                cnt += 1
    else:
        app.logger.error([f'Github API error:  {r.status_code} {author} {r.json()["message"]}'])

    return cnt


def send_slack_mention_msg(author, appended_msg=''):
    """config 에 등록된 채널에 특정 슬랙 메시지를 전송합니다. github author 에 해당되는 user 를 멘션합니다

                Keyword arguments:
                author -- 슬랙 메시지에 멘션할 github author. config_prod.json 에 등록해둔 user_id 를 사용
    """
    msg = f'<@{slack_cfg["user_id"][author]}>' + appended_msg

    send_slack_msg(msg)


def send_slack_msg(msg):
    headers = {'Authorization': f'Bearer {slack_cfg["token"]}'}
    body_data = {'channel': slack_cfg['channel_id'], 'text': msg}

    requests.post(SLACK_API_URL, data=body_data, headers=headers)


if __name__ == '__main__':
    app.config.from_object(Config())
    scheduler = APScheduler()
    scheduler.init_app(app)
    scheduler.start()

    # test()

    app.run('0.0.0.0', port=5002, debug=False)
