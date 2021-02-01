import datetime
import json
import logging
from logging.config import fileConfig
import re

import requests
from flask_apscheduler import APScheduler
from flask import Flask, jsonify, render_template, flash, redirect, url_for, request

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
SLACK_MSG_ERROR_PERIOD = '잘못된 기간을 입력했습니다.'


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
    send_msg_less_committer_days(since_days=checker_cfg['period_day'], author_infos=checker_cfg['whom'],
                                 keyword=checker_cfg['commit_keyword'])
    return 'working'


@app.route('/', methods=['GET'])
def home():
    info = {"repo": f'{git_cfg["repo"]["owner"]}/{git_cfg["repo"]["name"]}', "keyword": checker_cfg['commit_keyword']}

    return render_template('index.html', info=info)


@app.route('/commit/cnt', methods=["GET"])
def send_commit_cnt():
    keyword = checker_cfg['commit_keyword']
    author = request.args.get('username')
    since = request.args.get('since')
    until = request.args.get('until')

    commit_cnt = count_repo_commit_per_author(author, since, until, keyword)

    return jsonify({"author": author, "cnt": commit_cnt})


@app.route('/commit/slack', methods=["GET"])
def send_slack_msg():
    """
     목표 commit 갯수 정보가 config 에 없으면 0
    :return:
    """
    author = request.args.get('username')
    since = request.args.get('since')
    until = request.args.get('until')
    cnt = next((item['target_commit_count'] for item in checker_cfg['whom'] if item["committer"] == author), 0)

    send_slack_info_msg(keyword=checker_cfg['commit_keyword'], since=since, until=until,
                        author_infos=[{"committer": author, "target_commit_count": cnt}])

    return jsonify({"result": "succsss"})


def send_msg_less_committer_days(keyword='', since_days=1, until_days=0,
                                 author_infos=[{"committer": git_cfg['user'], "target_commit_count": 1}]):
    """ 특정 일 전부터 특정 일 전 까지의 keyword 를 포함하는 commit 수가 n개 미만이면,
    해당 사용자에게 멘션을 걸어 슬랙 알람 메시지를 전송합니다.
    유효하지 않은 기간 값을 입력할 경우, 잘못된 값 입력 안내 슬랙 메시지를 전송합니다.

    Keyword arguments:
        keyword --  regexp. 이 Regexp를 만족하는(포함하는) commit message 만 count 함.
        since_days -- 현재 시각 기준 since_days 일 전부터 commit 만 확인, 기본값 1
        until_days -- 현재 시각 기준 until_days 일 전까지 commit 만 확인, 기본값 현재 날짜
        author_info -- commit 수를 체크할 committer 와 committer 별 목표 commit 수
            e.g. {"committer": "repo-committer-user-name", "target_commit_count": 1}
        e.g. since_days = 2, until_days 입력하지 않음 -> 현재로부터 2일 전 commit 부터 현재까지 확인
        e.g. since_days = 5, until_days = 3 -> 현재로부터 5일 전 ~ 3일 전 commit 까지 확인
        e.g. since_days 입력하지 않음, until_days = 2 -> 유효하지 않은 값
        e.g. since_days = 1, until_days = 2 -> 유효하지 않은 값

    """

    if since_days < until_days:
        send_slack_msg(f'{SLACK_MSG_ERROR_PERIOD} 지금으로부터 {since_days}일 전 부터 {until_days}일 전 까지 데이터를 요청하셨습니다.')
        return

    # TODO : 00시부터 23:59 기준으로 바꾸기
    since_time = (datetime.datetime.now() - datetime.timedelta(days=since_days)).astimezone().isoformat()
    until_time = (datetime.datetime.now() - datetime.timedelta(days=until_days)).astimezone().isoformat()

    send_msg_less_committer_time(keyword=keyword, since=since_time, until=until_time, author_infos=author_infos)


# TODO : slack msg 중복 제거
def send_slack_info_msg(keyword='',
                        since=(datetime.datetime.now() - datetime.timedelta(days=1)).astimezone().isoformat(),
                        until=datetime.datetime.now().astimezone().isoformat(),
                        author_infos=[{"committer": git_cfg['user'], "target_commit_count": 1}]):
    """특정 시간 전부터 특정 시간 전 까지의 keyword 를 포함하는 commit 수 정보를,
    해당 사용자에게 멘션을 걸어 슬랙 알람 메시지를 전송합니다.
    유효하지 않은 기간 값을 입력할 경우, 잘못된 값 입력 안내 슬랙 메시지를 전송합니다.

    Keyword arguments:
        keyword --  regexp. 이 Regexp를 만족하는(포함하는) commit message 만 count 함.
        since -- 이 시간 이후 commit 만 확인. timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.
            e.g. 2021-01-02T01:24:25.944203+09:00 이후 commit 만 확인
        until -- 이 시간 이전 commit 만 확인. timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.
            e.g. 2021-02-02T01:24:25.944203+09:00 이전 commit 만 확인
        author_info -- commit 수를 체크할 committer 와 committer 별 목표 commit 수
            e.g. {"committer": "repo-committer-user-name", "target_commit_count": 1}
    """

    if since > until:
        send_slack_msg(f'{SLACK_MSG_ERROR_PERIOD} 지금으로부터 {since} 전 부터 {until} 전 까지 데이터를 요청하셨습니다.')
        return

    commit_info = count_repo_commit(since=since, until=until, author_infos=author_infos, keyword=keyword)

    for info in author_infos:
        author = info['committer']
        target_commit_cnt = info['target_commit_count']

        msg = f'실제 commit: {commit_info[author]} 개 / 목표 commmit : {target_commit_cnt} 개 ' + slack_cfg['msg']['format'].format(
            *slack_cfg['msg']['args'])
        send_slack_mention_msg(author, appended_msg=msg)


def send_msg_less_committer_time(keyword='',
                                 since=(datetime.datetime.now() - datetime.timedelta(days=1)).astimezone().isoformat(),
                                 until=datetime.datetime.now().astimezone().isoformat(),
                                 author_infos=[{"committer": git_cfg['user'], "target_commit_count": 1}]):
    """특정 시간 전부터 특정 시간 전 까지의 keyword 를 포함하는 commit 수가 n개 미만이면,
    해당 사용자에게 멘션을 걸어 슬랙 알람 메시지를 전송합니다.
    유효하지 않은 기간 값을 입력할 경우, 잘못된 값 입력 안내 슬랙 메시지를 전송합니다.

    Keyword arguments:
        keyword --  regexp. 이 Regexp를 만족하는(포함하는) commit message 만 count 함.
        since -- 이 시간 이후 commit 만 확인. timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.
            e.g. 2021-01-02T01:24:25.944203+09:00 이후 commit 만 확인
        until -- 이 시간 이전 commit 만 확인. timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.
            e.g. 2021-02-02T01:24:25.944203+09:00 이전 commit 만 확인
        author_info -- commit 수를 체크할 committer 와 committer 별 목표 commit 수
            e.g. {"committer": "repo-committer-user-name", "target_commit_count": 1}
    """

    if since > until:
        send_slack_msg(f'{SLACK_MSG_ERROR_PERIOD} 지금으로부터 {since} 전 부터 {until} 전 까지 데이터를 요청하셨습니다.')
        return

    commit_cnt = count_repo_commit(since=since, until=until, author_infos=author_infos, keyword=keyword)

    for info in author_infos:
        author = info['committer']
        target_commit_cnt = info['target_commit_count']
        if commit_cnt[author] < target_commit_cnt:
            msg = slack_cfg['msg']['format'].format(*slack_cfg['msg']['args'])
            send_slack_mention_msg(author, appended_msg=msg)


def count_repo_commit(keyword, since, until, author_infos):
    """현재부터 checked_date 후로 발생한 특정 repo commit 중,
    특정 키워드가 포함된 commit 수를 committer 별(config.json에 입력된 committer)로 반환합니다.

    Keyword arguments:
        since -- 이 시간 이후 commit 만 확인. timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.
            e.g. 2021-01-02T01:24:25.944203+09:00 이후 commit 만 확인
        until -- 이 시간 이전 commit 만 확인. timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.
            e.g. 2021-02-02T01:24:25.944203+09:00 이전 commit 만 확인
        author_info -- commit 수를 체크할 committer 와 committer 별 목표 commit 수
            e.g. {"committer": "repo-committer-user-name", "target_commit_count": 1}
        keyword --  regexp. 이 Regexp를 만족하는(포함하는) commit message 만 count 함.
    """

    result = {}

    for info in author_infos:
        author = info['committer']
        result[author] = count_repo_commit_per_author(since=since, until=until, author=author, keyword_regexp=keyword)

    return result


def count_repo_commit_per_author(author, since, until, keyword_regexp):
    """현재부터 checked_date 후로 발생한 특정 repo 의 author 의 commit 중,
    특정 키워드가 포함된 commit 수를 반환합니다.

    Keyword arguments:
        author_info -- commit 수를 체크할 committer 와 committer 별 목표 commit 수
                e.g. {"committer": "repo-committer-user-name", "target_commit_count": 1}
        since -- 이 시간 이후 commit 만 확인. timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.
            기본값: 현재 시간 24시간 전
            e.g. 2021-01-02T01:24:25.944203+09:00 이후 commit 만 확인
        until -- 이 시간 이전 commit 만 확인. timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.
            기본값 : 현재 시간
            e.g. 2021-02-02T01:24:25.944203+09:00 이전 commit 만 확인
        keyword_regexp --  regexp. 이 Regexp를 만족하는(포함하는) commit message 만 count 함.
                    기본값: 없음. 모든 commit 을 count
    """

    cnt = 0

    param = {'author': author, 'since': since, 'until': until}
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

    mention_msg = f'<@{slack_cfg["user_id"][author]}>' or author
    msg = mention_msg + appended_msg

    send_slack_msg(msg)


def send_slack_msg(msg):
    headers = {'Authorization': f'Bearer {slack_cfg["token"]}'}
    body_data = {'channel': slack_cfg['channel_id'], 'text': msg}

    requests.post(SLACK_API_URL, data=body_data, headers=headers)


if __name__ == '__main__':
    # app.config.from_object(Config())
    # scheduler = APScheduler()
    # scheduler.init_app(app)
    # scheduler.start()

    # test()

    app.run('0.0.0.0', port=5002, debug=True)
