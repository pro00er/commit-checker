import logging
from logging.config import fileConfig

import atexit

from apscheduler.schedulers.background import BackgroundScheduler

import requests
from flask import Flask
import json
import datetime

app = Flask(__name__)

fileConfig('logging.cfg')
logger = logging.getLogger('root')

with open('config.json', 'r') as f:
    config = json.load(f)

with open('custom.json', 'r') as f:
    custom = json.load(f)


# TODO: remove test url
@app.route('/', methods=['GET'])
def check_commit_yesterday():
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).astimezone().isoformat()

    result = count_commit(yesterday)

    for author in config['committer']:
        if result[author] == 0:
            send_slack_msg(author)

    return 'dummy'


def count_commit(checked_date):
    url = 'https://api.github.com/repos/{0}/{1}/commits'.format(config['repo']['owner'], config['repo']['name'])
    token_user = config['github']['user']
    token = config['github']['token']

    result = {}

    for author in config['committer']:
        param = {'author': author, 'since': checked_date}
        r = requests.get(url, params=param, auth=(token_user, token))

        if r.status_code == 200:
            commit_list = r.json()
            result[author] = len(commit_list)
        else:
            app.logger.error(['Github API error: ', r.status_code, r.json()['message']])

    return result


def send_slack_msg(author):
    url = 'https://slack.com/api/chat.postMessage'
    headers = {'Authorization': 'Bearer {}'.format(config['slack']['token'])}

    slack_user_id = config['slack']['user_id'][author]
    msg = '{0} <@{1}>'.format(custom['slack_msg'], slack_user_id)

    body_data = {'channel': config['slack']['channel_id'], 'text': msg}

    r = requests.post(url, data=body_data, headers=headers)


scheduler = BackgroundScheduler()
scheduler.add_job(func=check_commit_yesterday, trigger='cron', day_of_week=custom['scheduled']['day_of_week'],
                  hour=custom['scheduled']['hour'], minute=custom['scheduled']['minute'],
                  end_date=custom['scheduled']['end_date'])
scheduler.start()

# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    app.run('0.0.0.0', port=5002, debug=True)
