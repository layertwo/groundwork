# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/layertwo/groundwork/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                 |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| backend/\_\_init\_\_.py              |        0 |        0 |        0 |        0 |    100% |           |
| backend/config.py                    |       21 |        0 |        0 |        0 |    100% |           |
| backend/database.py                  |       13 |        7 |        0 |        0 |     46% |     27-33 |
| backend/dependencies/\_\_init\_\_.py |        0 |        0 |        0 |        0 |    100% |           |
| backend/dependencies/auth.py         |      128 |       31 |       40 |       12 |     72% |63, 71, 85-105, 129-130, 140-143, 148->150, 160, 167, 174, 178, 183, 192->194 |
| backend/dependencies/rate\_limit.py  |       20 |        2 |        2 |        1 |     86% |    19, 33 |
| backend/exceptions.py                |       26 |        1 |        0 |        0 |     96% |        34 |
| backend/main.py                      |       58 |       12 |        8 |        3 |     74% |33-44, 71, 85, 115 |
| backend/models/\_\_init\_\_.py       |        8 |        0 |        0 |        0 |    100% |           |
| backend/models/account.py            |       21 |        0 |        0 |        0 |    100% |           |
| backend/models/audit.py              |       21 |        0 |        0 |        0 |    100% |           |
| backend/models/base.py               |       11 |        0 |        0 |        0 |    100% |           |
| backend/models/job.py                |       21 |        0 |        0 |        0 |    100% |           |
| backend/models/role.py               |       21 |        0 |        0 |        0 |    100% |           |
| backend/models/role\_template.py     |        9 |        0 |        0 |        0 |    100% |           |
| backend/models/user.py               |       27 |        0 |        0 |        0 |    100% |           |
| backend/routers/\_\_init\_\_.py      |        0 |        0 |        0 |        0 |    100% |           |
| backend/routers/accounts.py          |       64 |        4 |       10 |        2 |     92% |55-57, 113, 118->117 |
| backend/routers/audit.py             |        5 |        0 |        0 |        0 |    100% |           |
| backend/routers/auth.py              |      115 |        8 |       22 |        5 |     91% |79-87, 155->171, 158->171, 195, 204, 210-212 |
| backend/routers/jobs.py              |       34 |        2 |       12 |        2 |     91% |    33, 37 |
| backend/routers/roles.py             |      182 |        7 |       46 |        7 |     94% |76, 102, 166, 170, 195-196, 239, 466->465 |
| backend/schemas/\_\_init\_\_.py      |        0 |        0 |        0 |        0 |    100% |           |
| backend/schemas/account.py           |       13 |        0 |        0 |        0 |    100% |           |
| backend/schemas/audit.py             |       13 |        0 |        0 |        0 |    100% |           |
| backend/schemas/auth.py              |        8 |        0 |        0 |        0 |    100% |           |
| backend/schemas/common.py            |        6 |        0 |        0 |        0 |    100% |           |
| backend/schemas/job.py               |        6 |        0 |        0 |        0 |    100% |           |
| backend/schemas/role.py              |       94 |       11 |       24 |       10 |     82% |20, 26, 29, 35, 38, 44, 47, 51, 100, 107, 113 |
| backend/schemas/role\_template.py    |       32 |        0 |       10 |        0 |    100% |           |
| backend/services/\_\_init\_\_.py     |        0 |        0 |        0 |        0 |    100% |           |
| backend/services/audit.py            |        6 |        0 |        0 |        0 |    100% |           |
| backend/services/aws.py              |      169 |       48 |       48 |        1 |     65% |31-33, 178-190, 195-202, 314->321, 338-397 |
| backend/services/crypto.py           |       13 |        0 |        0 |        0 |    100% |           |
| backend/services/jobs.py             |      214 |      133 |       26 |        4 |     39% |29-62, 85-90, 119->108, 122, 179-245, 250-311, 316-366, 381 |
| backend/services/oidc.py             |       78 |       26 |        4 |        0 |     68% |57-68, 93-123, 127-138 |
| **TOTAL**                            | **1457** |  **292** |  **252** |   **47** | **78%** |           |


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