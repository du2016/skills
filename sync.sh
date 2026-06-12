#!/bin/bash
TARGET_DIRS=(
    "/Users/shareit/.kiro/skills/"
    "/Users/shareit/.codex/skills/"
)

# 【配置项 2】定义排除的目录列表（可随意在括号内添加或删除，空格隔开）
EXCLUDE_DIRS=(
    "quant"
    "output"
)

echo "🚀 开始执行一键清空与多目标定向同步..."

# ------------------------------------------------------------------------------
# 第二步：遍历并清空所有的目标目录
# ------------------------------------------------------------------------------
echo "🧹 正在初始化并清空目标目录..."

for target in "${TARGET_DIRS[@]}"; do
    if [ -d "$target" ]; then
        # 清空内部内容（含隐藏文件），保留目标文件夹壳子本身
        rm -rf "$target"/* "$target"/.* 2>/dev/null
        echo "   -> 已清空: $target"
    else
        mkdir -p "$target"
        echo "   -> 已创建并初始化: $target"
    fi
done

echo "✨ 所有目标目录已就绪。"

# ------------------------------------------------------------------------------
# 第三步：遍历当前目录下的一级子目录并一键分发
# ------------------------------------------------------------------------------
echo "📂 正在同步当前层级的子目录本身..."

# 显式启用 nullglob，防止没有子目录时把 "*/" 当作字符串处理
shopt -s nullglob

# 遍历当前目录下的所有一级子目录
for dir in */; do
    # 检查确保是目录
    if [ -d "$dir" ]; then
        # 去掉目录末尾的斜杠（例如将 "quant/" 变成 "quant"）
        clean_dir="${dir%/}"
        
        # 检查当前目录是否在排除黑名单中
        should_skip=false
        for exclude in "${EXCLUDE_DIRS[@]}"; do
            if [ "$clean_dir" = "$exclude" ]; then
                should_skip=true
                break
            fi
        done
        
        # 如果命中黑名单，跳过
        if [ "$should_skip" = true ]; then
            echo "🚫 已跳过排除列表中的目录: $clean_dir"
            continue
        fi
        
        echo "   -> 正在整体复制子目录: $clean_dir"
        
        # 遍历目标列表，一键分发复制到所有目的地
        for target in "${TARGET_DIRS[@]}"; do
            cp -R "$clean_dir" "$target"
        done
    fi
done

echo "--------------------------------------------------"
echo "🎉 完美搞定！所有非排除目录已成功一键同步到列表中的所有目标位置。"