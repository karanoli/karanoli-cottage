# karanoli的小屋维护说明

这份文档面向后续维护与加设功能。项目采用 Django 单应用结构：`sudoku_site` 负责全站配置，`game` 同时承载博客、账户和数独小游戏。修改数据模型后应同步检查并执行数据库迁移。

## 一、目录与每个文件的作用

### 项目根目录

| 文件 | 作用 |
| --- | --- |
| `README.md` | 面向使用者的安装、启动、文章发布和功能说明。 |
| `MAINTENANCE.md` | 本文件，面向开发维护者说明结构、数据流和扩展位置。 |
| `项目展示与简历说明.md` | 简历中的项目描述、可演示路径、面试讲解要点与目前限制。 |
| `.gitignore` | 排除本地数据库、上传文件、环境变量、缓存、虚拟环境及非公开截图。 |
| `manage.py` | Django 命令入口；执行启动、迁移、配置检查、初始化题库等任务。 |
| `requirements.txt` | Python 依赖版本范围。新增第三方库时同步更新。 |
| `db.sqlite3` | 默认开发数据库，保存用户、密码哈希、文章、题库和游戏记录；不要手工编辑，上线前应备份并改用正式数据库。 |

### `sudoku_site/`：全站配置

| 文件 | 作用 |
| --- | --- |
| `sudoku_site/__init__.py` | 标记 Django 项目配置包。 |
| `sudoku_site/settings.py` | 数据库、语言时区、静态/媒体目录、密码校验器以及游戏经济参数。 |
| `sudoku_site/urls.py` | 总路由；连接管理后台、登录/退出和 `game` 应用。开发模式下也提供媒体文件。 |
| `sudoku_site/asgi.py` | ASGI 部署入口。 |
| `sudoku_site/wsgi.py` | WSGI 部署入口。 |

### `game/`：核心业务代码

| 文件 | 作用 |
| --- | --- |
| `game/__init__.py` | 标记核心应用包。 |
| `game/apps.py` | 应用启动配置，并在启动时加载账户信号。 |
| `game/models.py` | 所有持久化模型：文章、文章评论、用户档案、题组、题目、游戏会话、操作记录、提示记录、金币流水和投稿。 |
| `game/forms.py` | 注册、纯文本评论和投稿上传表单；修改密码直接使用 Django 的安全表单。 |
| `game/views.py` | 页面与接口控制层；包含博客评论及其权限、注册回跳、改密、游戏、提示、金币奖励和投稿流程。 |
| `game/urls.py` | `game` 内部路由。新增页面或接口时在这里登记。 |
| `game/sudoku.py` | 与网页无关的数独算法：格式校验、求解、唯一解计数、难度估计和教学提示。 |
| `game/ocr.py` | OpenCV 棋盘定位与 Tesseract 单格数字识别；识别失败时允许人工校正。 |
| `game/admin.py` | 后台管理显示、文章上传字段和题库 JSON 导出。 |
| `game/signals.py` | 创建用户时自动创建 `UserProfile`，保证金币与提示字段可直接使用。 |
| `game/tests.py` | 业务回归检查，覆盖文章、评论权限与转义、注册回跳、游戏状态和题目投稿等流程。 |

### `game/management/`：维护命令

| 文件 | 作用 |
| --- | --- |
| `game/management/__init__.py` | 自定义维护命令包。 |
| `game/management/commands/__init__.py` | Django 命令模块包。 |
| `game/management/commands/seed_sudoku.py` | 幂等创建四个难度组和示例题。 |
| `game/management/commands/import_puzzles.py` | 从 JSON 批量导入题目，并在入库前检查格式、规则和唯一解。 |

### `game/migrations/`：数据库版本

| 文件 | 作用 |
| --- | --- |
| `game/migrations/__init__.py` | 标记迁移包。 |
| `game/migrations/0001_initial.py` | 建立数独题库、会话、日志、金币和投稿表。 |
| `game/migrations/0002_article.py` | 建立文章表。 |
| `game/migrations/0003_article_markdown_upload.py` | 增加 Markdown 文件来源并调整文章字段。 |
| `game/migrations/0004_puzzlesubmission_solution_image_optional.py` | 将旧版答案图片改为可选字段，使新版投稿只需上传题面。 |
| `game/migrations/0005_clear_obsolete_submission_errors.py` | 清除旧草稿中与答案图片相关的过时校验提示。 |
| `game/migrations/0006_puzzlesubmission_image_optional.py` | 允许直接输入题面时创建不含图片的投稿草稿。 |
| `game/migrations/0007_gamesession_wrong_values.py` | 为游戏会话增加独立错误数字网格，使错误输入可以持久标红。 |
| `game/migrations/0008_articlecomment.py` | 创建文章评论表，记录关联文章、作者、正文、可见状态与时间。 |

迁移文件代表历史数据库结构，通常不应回改。模型变化后使用 `python manage.py makemigrations` 生成新迁移，再执行 `python manage.py migrate`。

### `game/templates/game/`：页面模板

| 文件 | 作用 |
| --- | --- |
| `base.html` | 全站 HTML 骨架、导航、样式加载和消息提示。 |
| `home.html` | 博客主页、人物图、最近文章和小游戏入口。 |
| `article_list.html` | 已发布文章列表与分页。 |
| `article_detail.html` | Markdown/KaTeX 正文、分页评论、登录用户评论表单和游客注册提示。 |
| `login.html` | 登录页。 |
| `register.html` | 注册页。 |
| `password_change.html` | 登录用户修改密码；提交当前密码和两次新密码。 |
| `profile.html` | 个人统计、改密入口、做题记录、金币流水与投稿记录。 |
| `group_list.html` | 按“简单→中等→困难→专家”展示数独难度。 |
| `puzzle_list.html` | 某个难度下的题目及用户进度。 |
| `game.html` | 数独棋盘、五个工具、数字键盘、提示和结果弹窗。 |
| `submit.html` | 选择上传单张题面图或直接输入题面。 |
| `confirm_submission.html` | 人工录入或校正 OCR 题面；值为 0 的格子显示为空白，再交给程序求解与校验。 |

### `game/static/game/`：浏览器资源

| 文件 | 作用 |
| --- | --- |
| `style.css` | 全站基础组件与蓝色数独界面样式。 |
| `blog.css` | “karanoli的小屋”品牌首页、导航和账户页样式。 |
| `article.css` | 文章列表、首页文章预览及 Markdown/KaTeX 正文排版。 |
| `game.js` | 棋盘渲染、选格、数字/笔记输入、Shift/Tab 快捷键、计时、保存、撤销和提示交互。 |
| `images/karanoli-icon.jpeg` | 站点头像、主页人物图和浏览器图标。 |

### `game/templatetags/`：模板工具

| 文件 | 作用 |
| --- | --- |
| `game/templatetags/__init__.py` | 标记自定义模板标签包。 |
| `game/templatetags/game_extras.py` | 提供字典取值和秒数转 `分:秒` 的模板过滤器。 |

### 运行时目录

| 目录 | 作用 |
| --- | --- |
| `media/articles/` | 管理员上传的 Markdown 原文件。 |
| `media/submissions/` | 玩家上传的题面图；旧数据中可能仍包含答案图。 |
| `staticfiles/` | 执行 `collectstatic` 后生成的部署资源，不应手工修改。 |
| `__pycache__/` | Python 自动生成的字节码缓存，可安全重新生成。 |

## 二、核心数据流

### 文章发布

1. 管理员在后台只上传一个 UTF-8 编码的 `.md` 或 `.markdown` 文件。
2. `Article.save()` 读取文件正文；首次保存且标题为空时使用文件名作为标题，从首段生成摘要，并生成不冲突的网址标识。管理员后续修改标题不会被覆盖。
3. `views.article_list` 和 `views.article_detail` 只查询“已发布且发布时间不晚于当前时间”的文章。
4. 详情页先用 marked 解析 Markdown，再用 KaTeX 渲染 `$...$`、`$$...$$`、`\(...\)` 和 `\[...\]`。

若要增加文章分类或标签：先在 `Article` 增加模型字段或关联模型，再生成迁移，随后更新 `admin.py` 与文章模板。

### 文章评论

1. `ArticleComment` 通过外键关联文章和用户。删除文章会连带删除评论；删除用户后保留评论正文，作者显示为“已注销用户”。
2. `article_detail` 只对公开文章展示 `is_visible=True` 的评论，每页 20 条；`select_related("user")` 随评论查询作者。
3. `ArticleCommentForm` 去除首尾空白，并拒绝空评论及超过 2000 字的正文。创建视图通过 `request.user` 绑定作者，不接受客户端指定作者。
4. `article_comment_create` 只允许登录后的 POST，成功后重定向回文章评论位置；Django CSRF 中间件校验写操作。
5. 评论独立于 marked 渲染，模板使用自动转义与 `linebreaksbr` 显示纯文本，不能对评论增加 `safe` 过滤器。
6. `article_comment_delete` 重新检查作者身份；后台“文章评论”支持检索、隐藏、恢复和删除。
7. 游客看到注册、登录入口，链接携带站内 `next`；注册视图用 `url_has_allowed_host_and_scheme` 校验回跳，避免外站重定向。

### 账户与修改密码

1. 注册使用 `RegistrationForm`；`signals.py` 自动创建对应的 `UserProfile`。
2. 修改密码地址为 `/account/password/`，必须先登录。
3. `PasswordChangeForm` 会验证当前密码、两次新密码及 `settings.py` 中的密码规则。
4. 保存后调用 `update_session_auth_hash`，因此当前设备不会被登出；旧密码立即失效。

不要自行保存明文密码，也不要直接修改 `User.password`。后台重置密码应使用 Django Admin 的“更改密码”入口。

### 数独游戏

1. `group_list` 按 `sort_order`、`id` 固定排序；游客只看到简单题。
2. 打开题目时 `_get_session` 为登录用户读取或创建持久会话；游客会话每次打开都重置。
3. `game.js` 处理键盘和按钮：方向键移动，Shift 切换小数字输入，Tab 显示/隐藏笔记。`highlightedDigit` 是正式数字与候选小数字共用的高亮状态；点击候选小数字或输入小数字后，会同步高亮全盘同值候选。
4. 正式数字由 `game_move` 在服务端与答案比对；正确数字写入 `board`，同时从同行、同列、同宫的笔记中删除该数字；错误数字写入独立的 `wrong_values` 并累计一次错误。
5. 错误数字会持续标红；用户换填后重新判断，仍错则更新红色数字并再次计错，正确则清除错误值并写入正式棋盘。
6. 同一格已有正确数字时，必须先删除才可改填，避免被其他数字直接覆盖。
7. 满盘正确后，事务内发放对应难度奖励且只发一次。
8. 右侧“新游戏”提交 `new_game`，按 `sequence`、`id` 进入同题组的下一题，并保留当前题的已登录用户进度。
9. 完成或累计三次错误后，结果弹窗内提交 `reset_game`，只清空并重玩当前题。若题组只有一题，`new_game` 也会循环回当前题并开启新局。

若要增加第六个游戏工具：先改 `game.html` 的工具栏，再在 `game.js` 添加状态和事件，最后进行页面与接口联调。

### 智能提示与金币

1. 每日免费次数由 `UserProfile.refresh_daily_hints()` 在跨日访问时重置。
2. `game_hint` 在数据库事务中选择免费或金币支付，并同时写入提示日志与金币流水。
3. `sudoku.find_hint()` 返回说明、涉及格子、候选数排除或下一步填数，不直接改棋盘。
4. 金币价格和每日次数由 `settings.py` 的 `SUDOKU_HINT_COIN_COST`、`SUDOKU_DAILY_FREE_HINTS` 控制。

### 题目投稿

1. 投稿表单提供“上传图片”和“直接输入”两种方式，均不要求玩家提供答案。
2. 图片文件先受 8 MB 大小限制，再保存为 `PuzzleSubmission`；直接输入则创建不含图片的草稿。
3. 图片模式由 `ocr.py` 透视矫正棋盘并逐格识别；直接输入从空白 9×9 网格开始。
4. 校正页将 JSON 中的 0 显示为空白，提交时空白由 `_grid_from_post()` 转回 0。
5. 服务端检查重复数字并最多搜索两个解；只有唯一解题目才调用 `solve_grid()` 生成完整答案，再自动评估难度。
6. 审核开关关闭时自动入库并奖励 5 金币；开启时进入待审核状态。

## 三、常见扩展位置

| 目标 | 主要修改位置 | 同步检查 |
| --- | --- | --- |
| 新增博客字段/分类 | `models.py`、`admin.py`、文章模板 | 新迁移、前后台联调 |
| 修改首页内容 | `home.html`、`blog.css` | 桌面宽度视觉检查 |
| 新增账户功能 | `views.py`、`urls.py`、账户模板 | 登录保护、CSRF、权限检查 |
| 调整数独规则 | `sudoku.py`、`views.py`、`game.js` | 算法结果、接口联调 |
| 新增提示技巧 | `sudoku.find_hint()` | 使用典型盘面验证说明与结果 |
| 调整金币经济 | `settings.py`、`views.py` | 流水与重复奖励检查 |
| 新增题库批处理 | `management/commands/` | 输入校验和幂等性 |
| 调整数据结构 | `models.py` | 新迁移、备份与回滚方案 |

## 四、维护命令

```bash
# 安装与迁移
python -m pip install -r requirements.txt
python manage.py migrate

# 初始化或修复示例题库（可重复执行）
python manage.py seed_sudoku

# 检查配置和迁移状态
python manage.py check
python manage.py makemigrations --check --dry-run

# 本地运行
python manage.py runserver
```

批量导入题目：

```bash
python manage.py import_puzzles 路径/题库.json
```

## 五、上线前检查

- 设置随机且保密的 `DJANGO_SECRET_KEY`，并关闭 `DJANGO_DEBUG`。
- 设置正确的 `DJANGO_ALLOWED_HOSTS`，启用 HTTPS 和安全 Cookie。
- 使用 PostgreSQL 等正式数据库，并备份 `db.sqlite3` 和 `media/` 后再迁移。
- 通过 Web 服务器提供 `collectstatic` 生成的静态资源，媒体目录设置独立备份。
- 管理员密码不要写入源码或提交到版本管理；定期更换，并限制后台访问。
- 对文章 Markdown 做可信来源管理；当前设计只有管理员能够发布文章。
- 每次上线前运行配置检查和迁移检查，并在浏览器中完成关键流程验证。
