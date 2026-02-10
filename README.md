# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/layertwo/groundwork/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                 |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| backend/\_\_init\_\_.py              |        0 |        0 |        0 |        0 |    100% |           |
| backend/config.py                    |       23 |        0 |        0 |        0 |    100% |           |
| backend/database.py                  |       13 |        7 |        0 |        0 |     46% |     27-33 |
| backend/dependencies/\_\_init\_\_.py |        0 |        0 |        0 |        0 |    100% |           |
| backend/dependencies/auth.py         |       69 |       20 |       18 |        3 |     69% |53, 61, 75-95 |
| backend/dependencies/rate\_limit.py  |       20 |        2 |        2 |        1 |     86% |    19, 33 |
| backend/exceptions.py                |       32 |        3 |        0 |        0 |     91% | 38, 51-52 |
| backend/main.py                      |      128 |       70 |       26 |        3 |     40% |45-59, 64-84, 89-101, 106-145, 172, 186, 217-229 |
| backend/models/\_\_init\_\_.py       |        8 |        0 |        0 |        0 |    100% |           |
| backend/models/account.py            |       22 |        0 |        0 |        0 |    100% |           |
| backend/models/audit.py              |       21 |        0 |        0 |        0 |    100% |           |
| backend/models/base.py               |       11 |        0 |        0 |        0 |    100% |           |
| backend/models/job.py                |       22 |        0 |        0 |        0 |    100% |           |
| backend/models/role.py               |       23 |        0 |        0 |        0 |    100% |           |
| backend/models/role\_template.py     |        9 |        0 |        0 |        0 |    100% |           |
| backend/models/user.py               |       27 |        0 |        0 |        0 |    100% |           |
| backend/routers/\_\_init\_\_.py      |        0 |        0 |        0 |        0 |    100% |           |
| backend/routers/accounts.py          |       64 |        4 |       10 |        2 |     92% |55-57, 113, 118->117 |
| backend/routers/audit.py             |        5 |        0 |        0 |        0 |    100% |           |
| backend/routers/auth.py              |      115 |        8 |       22 |        5 |     91% |79-87, 155->171, 158->171, 195, 204, 210-212 |
| backend/routers/jobs.py              |       52 |        2 |       16 |        2 |     94% |    84, 88 |
| backend/routers/roles.py             |      197 |        8 |       60 |        8 |     94% |72, 98, 162, 169, 197-198, 257, 340, 491->490 |
| backend/schemas/\_\_init\_\_.py      |        0 |        0 |        0 |        0 |    100% |           |
| backend/schemas/account.py           |       13 |        0 |        0 |        0 |    100% |           |
| backend/schemas/audit.py             |       13 |        0 |        0 |        0 |    100% |           |
| backend/schemas/auth.py              |        8 |        0 |        0 |        0 |    100% |           |
| backend/schemas/common.py            |        6 |        0 |        0 |        0 |    100% |           |
| backend/schemas/job.py               |        8 |        0 |        0 |        0 |    100% |           |
| backend/schemas/role.py              |       92 |       11 |       24 |       10 |     82% |20, 26, 29, 35, 38, 44, 47, 51, 100, 107, 113 |
| backend/schemas/role\_template.py    |       32 |        0 |       10 |        0 |    100% |           |
| backend/services/\_\_init\_\_.py     |        0 |        0 |        0 |        0 |    100% |           |
| backend/services/audit.py            |        6 |        0 |        0 |        0 |    100% |           |
| backend/services/aws.py              |      240 |       34 |       64 |        6 |     80% |41-43, 178, 307->314, 329-367, 393-401, 449, 534, 591, 608 |
| backend/services/crypto.py           |       13 |        0 |        0 |        0 |    100% |           |
| backend/services/jobs.py             |      402 |      105 |       76 |       10 |     73% |71-127, 150-155, 184->173, 187, 257-262, 386-387, 389-390, 392-393, 414, 434-449, 602-660, 747, 752 |
| backend/services/oidc.py             |       79 |       26 |        4 |        0 |     69% |58-69, 94-124, 128-139 |
| backend/services/system\_user.py     |       14 |        0 |        2 |        0 |    100% |           |
| **TOTAL**                            | **1787** |  **300** |  **334** |   **50** | **81%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/layertwo/groundwork/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/layertwo/groundwork/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/layertwo/groundwork/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/layertwo/groundwork/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Flayertwo%2Fgroundwork%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/layertwo/groundwork/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.