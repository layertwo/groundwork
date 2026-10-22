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
| backend/main.py                      |      132 |       70 |       28 |        3 |     42% |46-60, 65-85, 90-102, 107-146, 173, 187, 232-244 |
| backend/models/\_\_init\_\_.py       |        8 |        0 |        0 |        0 |    100% |           |
| backend/models/account.py            |       24 |        0 |        0 |        0 |    100% |           |
| backend/models/audit.py              |       21 |        0 |        0 |        0 |    100% |           |
| backend/models/base.py               |       11 |        0 |        0 |        0 |    100% |           |
| backend/models/job.py                |       22 |        0 |        0 |        0 |    100% |           |
| backend/models/role.py               |       25 |        0 |        0 |        0 |    100% |           |
| backend/models/role\_template.py     |        9 |        0 |        0 |        0 |    100% |           |
| backend/models/user.py               |       28 |        0 |        0 |        0 |    100% |           |
| backend/routers/\_\_init\_\_.py      |        0 |        0 |        0 |        0 |    100% |           |
| backend/routers/accounts.py          |       86 |        4 |       24 |        3 |     94% |69-71, 127, 144-\>143, 150-\>152 |
| backend/routers/audit.py             |       27 |        2 |        8 |        2 |     89% |    37, 39 |
| backend/routers/auth.py              |      117 |        8 |       22 |        5 |     91% |79-87, 158-\>174, 161-\>174, 198, 207, 213-215 |
| backend/routers/events.py            |       43 |       29 |        6 |        0 |     29% |     28-63 |
| backend/routers/jobs.py              |       52 |        2 |       16 |        2 |     94% |    89, 93 |
| backend/routers/roles.py             |      232 |       10 |       66 |       10 |     93% |78, 97, 164, 171, 199-200, 261, 324, 335, 410, 573-\>572 |
| backend/schemas/\_\_init\_\_.py      |        0 |        0 |        0 |        0 |    100% |           |
| backend/schemas/auth.py              |        8 |        0 |        0 |        0 |    100% |           |
| backend/schemas/common.py            |        6 |        0 |        0 |        0 |    100% |           |
| backend/schemas/federate.py          |        3 |        0 |        0 |        0 |    100% |           |
| backend/schemas/generated\_base.py   |       14 |        0 |        4 |        0 |    100% |           |
| backend/schemas/validation.py        |       18 |        4 |        6 |        2 |     75% |22-23, 30, 35 |
| backend/services/\_\_init\_\_.py     |        0 |        0 |        0 |        0 |    100% |           |
| backend/services/audit.py            |        6 |        0 |        0 |        0 |    100% |           |
| backend/services/aws.py              |      309 |       41 |       68 |        7 |     82% |45-47, 182, 311-\>318, 333-371, 397-405, 468, 504-512, 611, 696, 753, 770 |
| backend/services/crypto.py           |       13 |        0 |        0 |        0 |    100% |           |
| backend/services/events.py           |       37 |       11 |        6 |        1 |     67% |26-31, 34, 39-42 |
| backend/services/jobs.py             |      486 |      130 |      104 |       15 |     72% |80-141, 164-169, 200-\>189, 203, 277-282, 343, 348, 371-372, 389-390, 486-487, 489-490, 492-493, 514, 526-539, 561-577, 738-800, 887, 892 |
| backend/services/oidc.py             |       79 |       26 |        4 |        0 |     69% |58-69, 94-124, 128-139 |
| backend/services/system\_user.py     |       14 |        0 |        2 |        0 |    100% |           |
| **TOTAL**                            | **1987** |  **369** |  **384** |   **54** | **79%** |           |


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