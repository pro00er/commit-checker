import datetime
import json
import logging
from logging.config import fileConfig

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from flask_apscheduler import APScheduler
from flask import Flask

app = Flask(__name__)

fileConfig('logging.cfg')
logger = logging.getLogger('root')

# MODE = 'prod' || 'dev'
MODE = 'dev'

with open('config_{}.json'.format(MODE), 'r') as f:
    config = json.load(f)

git_config = config['github']
slack_config = config['slack']


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


# TODO: remove test url
# @app.route('/', methods=['GET'])
def send_msg_to_zero_committer(n_days=1):
    """현재부터 24* n 시간 전(n일 전)까지의 commit 수가 0이면, 해당 사용자에게 슬랙 알람 메시지를 전송합니다.

        Keyword arguments:
        n_days -- 지금으로부터 n 일 전 (기본값 1)
    """
    before_date = (datetime.datetime.now() - datetime.timedelta(days=n_days)).astimezone().isoformat()

    result = count_commit(before_date)

    for author in git_config['committer']:
        if result[author] == 0:
            send_slack_mention_msg(author)

    return 'dummy'


def count_commit(checked_date):
    """현재부터 checked_date 후로 발생한 특정 repo commit 수를 commiter별(config.json에 입력된 commiter)로 확인합니다.

            Keyword arguments:
            checked_date -- timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.
    """
    url = f'https://api.github.com/repos/{git_config["repo"]["owner"]}/{git_config["repo"]["name"]}/commits'
    token_user = git_config['user']
    token = git_config['token']

    result = {}

    for author in git_config['committer']:
        param = {'author': author, 'since': checked_date}
        r = requests.get(url, params=param, auth=(token_user, token))

        if r.status_code == 200:
            commit_list = r.json()
            result[author] = len(commit_list)
        else:
            app.logger.error(['Github API error: ', r.status_code, r.json()['message']])

    return result


# TODO
def count_keyword_commit(checked_date, keywords):
    """현재부터 checked_date 후로 발생한 특정 repo commit 중,
    특정 키워드가 포함된 commit 수를 commiter 별로 반환합니다.

            Keyword arguments:
            checked_date -- timestamp in ISO 8601 format: YYYY-MM-DDTHH:MM:SSZ.
    """

    url = f'https://api.github.com/repos/{git_config["repo"]["owner"]}/{git_config["repo"]["name"]}/commits'
    token_user = git_config['user']
    token = git_config['token']

    result = {}

    for author in git_config['committer']:
        param = {'author': author, 'since': checked_date}
        r = requests.get(url, params=param, auth=(token_user, token))

        if r.status_code == 200:
            commit_list = r.json()
            # specific_commits = commit_list['commit_message'].contain(keywords)
            # result[author] = len(specific_commits)
        else:
            app.logger.error(['Github API error: ', r.status_code, r.json()['message']])

    return result


def send_slack_mention_msg(author):
    """config 에 등록된 채널에 특정 슬랙 메시지를 전송합니다. github author 에 해당되는 user 를 멘션합니다

                Keyword arguments:
                author -- 슬랙 메시지에 멘션할 github author. config_prod.json 에 등록해둔 user_id 를 사용
    """
    msg = f'<@{slack_config['user_id'][author]}> ' + slack_config['msg']['format'].format(*slack_config['msg']['args'])

    send_slack_msg(msg)


def send_slack_msg(msg):
    url = 'https://slack.com/api/chat.postMessage'
    headers = {'Authorization': f'Bearer {slack_config["token"]}'}
    body_data = {'channel': slack_config['channel_id'], 'text': msg}

    requests.post(url, data=body_data, headers=headers)


# Set schedule
# scheduler = BackgroundScheduler(timezone=custom['scheduled']['timezone'])
# scheduler.add_job(func=check_commit_yesterday, trigger='cron', day_of_week=custom['scheduled']['day_of_week'],
#                   hour=custom['scheduled']['hour'], minute=custom['scheduled']['minute'],
#                   end_date=custom['scheduled']['end_date'])
#
# scheduler = BackgroundScheduler(timezone=custom['dev']['scheduled']['timezone'])
# scheduler.add_job(func=test, trigger='cron', day_of_week=custom['dev']['scheduled']['day_of_week'],
#                   hour=custom['dev']['scheduled']['hour'], minute=custom['dev']['scheduled']['minute'],
#                   end_date=custom['dev']['scheduled']['end_date'])
#
# scheduler.start()
#
# # Shut down the scheduler when exiting the app
# atexit.register(lambda: scheduler.shutdown())


if __name__ == '__main__':
    app.config.from_object(Config())
    scheduler = APScheduler()
    scheduler.init_app(app)
    scheduler.start()

    app.run('0.0.0.0', port=5002, debug=True)
