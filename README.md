# commit-checker
[![made-with-Markdown](https://img.shields.io/badge/Made%20with-Markdown-1f425f.svg)](http://commonmark.org)
[![Maintenance](https://img.shields.io/badge/Maintained%3F-yes-green.svg)](https://github.com/pro00er/commit-checker/graphs/commit-activity) 
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=flat-square)](http://makeapullrequest.com)


- 특정 github repository 특정 사용자가 에 매일매일 커밋했는지 확인합니다. 커밋되지 않았을 경우 슬랙 채널에 알람 메시지를 전송합니다. 
- 매일 매일 프로젝트에 기여하는 습관을 기르기 위한 도우미입니다. 일일 회고를 기록하는 스터디 그룹 리포지토리에 사용할 예정입니다. 

## 핵심 기능  Key Feature
- 특정 github repository의 특정 사용자의 기간별 커밋 수를 확인합니다. 
- 설정값에 미치지 못하는 commit 수일 경우, 슬랙 채널에 알람 메시지를 전송합니다. 

## 사용 How To Use
- 설정파일 변경
  - 설정파일 예제(config.json.example)에서 github, slack 정보를 업데이트 한 후, config.json 으로 이름을 바꿔주세요.
- 세부 설정 변경
  - custom.json 에서 슬랙 메시지, 정기적으로 실행되는 주기를 변경할 수 있습니다.

## Contributing
- Thanks to [@ohahohah](https://github.com/ohahohah)

## Reference
- [slack 메시지 전송 API](https://api.slack.com/messaging/sending)
- [github commit list API](https://docs.github.com/en/rest/reference/repos#commits)

## Links
- Repository: https://github.com/pro00er/commit-checker
- Issue tracker: https://github.com/pro00er/commit-checker/issues
  - 보안 취약점 등의 민감한 이슈인 경우 ohahohah.dev at gmail.com 로 연락주십시오. 

## License
오시영 – ohahohah.dev at gmail.com

MIT license를 준수합니다. [LICENSE](https://github.com/pro00er/commit-checker/LICENSE.md)에서 자세한 정보를 확인할 수 있습니다.  
