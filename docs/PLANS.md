# 方案是怎么回事（以及怎么自己定）

## 先搞清三样东西

| 东西 | 在哪 | 谁负责改 |
|---|---|---|
| 默认配置 | `configs/default.yaml` | 项目作者，随版本更新 |
| 本地方案写入 | `configs/local.yaml`（不进仓库） | `cover plan --apply` 或界面「用这套」 |
| 方案库 | `plans/*.yaml` | 内置 11 套 + 你自己加的 |

**关键点：方案不是必须的。** 不套任何方案，程序照样按 `default.yaml` 的默认值跑。
方案只做一件事——把 `separate / convert / train / clip / mix` 这五段参数**一次性写好**，并留个标记方便回滚。

`tools`（ffmpeg、RVC、UVR 路径）、`source`（音源搜索目录）、`providers`（发布/解密插件）这几段方案**永远不碰**，你自己填的会原样保留。

## 三种人选法

### 1. 手上配置已经跑通了，不想动

什么都别点。界面「方案」页会显示「当前方案：未设置」，但下面的默认值本来就是可用的一套（分离 becruily、RVC index 0.75 / protect 0.5、训练 80 轮、副歌 45 秒、响度 -14 LUFS）。

### 2. 想留个标记、方便以后回滚

点一套最接近你现状的卡片上的「用这套」。它会做三件事：

1. 把五段参数写进 `configs/local.yaml`
2. 记下 `plan: {id, name, applied_at}`
3. 写之前自动备份成 `local.yaml.bak-时间戳`

以后想回去：点「撤销方案」，五段恢复成 `default.yaml` 的值，`plan` 标记删掉，同样先备份。

### 3. 想自己定

看下面的「自定义方案」。

## 自定义方案

```bash
cp plans/_template.yaml plans/my_plan.yaml
# 改 id / name / for / scores / params / estimate
```

然后回界面点「重新推荐」，或者命令行 `cover plan`，你的方案就会出现在列表里，和内置的一视同仁。

### 字段说明（只讲会生效的部分）

| 字段 | 作用 |
|---|---|
| `id` | 唯一标识，`--apply` 用它；同一个 id 只能有一套 |
| `for.min_vram_gb` / `max_vram_gb` | 显存不在区间就排除（比上限大也算排除，因为"有更合适的"） |
| `for.gpu_required` | 没有独显时是否排除 |
| `for.min_disk_gb` | 磁盘不够就排除 |
| `for.needs_train` | `yes` 必须训练 / `no` 不支持训练 / `optional` 都行；和界面上「会不会训练」交叉过滤 |
| `scores` | 1~5 分，按「最在意」加权算总分：音质 3:0.5:0.3:1、速度、省空间、稳定各有权重 |
| `params` | 真正写进配置的五段，字段名和 `configs/default.yaml` 一致 |
| `estimate.vram_peak_gb` | 会跟界面上的「显存预算」比较，超了直接排除 |
| `estimate.per_song_minutes` | 超过「单曲可等分钟数」会扣分并提示 |
| `pros` / `cons` / `explain` | 卡片原样展示，**写清代价**，别只写好处 |

### 只改一点点怎么办

两种办法，看你要不要保留「可回滚」：

- **改方案文件**：把内置方案复制一份，改几个数，保存成新 id。好处是能一键套用/撤销。
- **直接改 `configs/local.yaml`**：只想微调一两个值（比如 `protect` 从 0.5 改 0.55）就直接改，最省事；坏处是没有 `plan` 标记，也就没有「撤销方案」按钮。

### 不想让某套方案出现

- 删掉 `plans/xxx.yaml`，或者
- 把 `for.min_vram_gb` 改成你的显卡永远达不到的数值，或者
- 加 `advanced: true`，默认不给新手推荐（勾了「进阶」才出现）

## 方案和「诊断」「配方」的区别

- **方案**解决"我这台机器该用什么参数"——一次性、全局的
- **配方**解决"这一首歌出了某个毛病该怎么修"——针对具体症状，可以 A/B 对比，选择会记进 `decisions.jsonl`

两者不冲突：先用方案打好底，个别歌有问题再走诊断。
