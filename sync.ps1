$TargetDirs = @(
    "C:\Users\shareit\.kiro\skills"
    "C:\Users\shareit\.codex\skills"
)

# 【配置项 2】定义排除的目录列表
$ExcludeDirs = @(
    "quant"
)

Write-Host "🚀 开始执行 Windows 一键清空与多目标定向同步..." -ForegroundColor Cyan

# ------------------------------------------------------------------------------
# 第二步：遍历并清空所有的目标目录
# ------------------------------------------------------------------------------
Write-Host "🧹 正在初始化并清空目标目录..." -ForegroundColor Yellow

foreach ($target in $TargetDirs) {
    if (Test-Path $target) {
        # 清空内部所有文件和文件夹，-Force 确保隐藏文件也被清除，-Recurse 递归删除
        Remove-Item "$target\*" -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "   -> 已清空: $target" -ForegroundColor Gray
    } else {
        # 如果目标目录不存在，则直接创建
        New-Item -ItemType Directory -Path $target -Force | Out-Null
        Write-Host "   -> 已创建并初始化: $target" -ForegroundColor Gray
    }
}

Write-Host "✨ 所有目标目录已就绪。" -ForegroundColor Green

# ------------------------------------------------------------------------------
# 第三步：遍历当前目录下的一级子目录并一键分发
# ------------------------------------------------------------------------------
Write-Host "📂 正在同步当前层级的子目录本身..." -ForegroundColor Yellow

# 获取当前目录下的一级子目录（排除文件）
$subDirs = Get-ChildItem -Directory

foreach ($dir in $subDirs) {
    $dirName = $dir.Name
    
    # 检查当前子目录是否在排除黑名单中
    if ($ExcludeDirs -contains $dirName) {
        Write-Host "🚫 已跳过排除列表中的目录: $dirName" -ForegroundColor DarkYellow
        continue
    }
    
    Write-Host "   -> 正在整体复制子目录: $dirName" -ForegroundColor White
    
    # 遍历目标列表，一键分发复制
    foreach ($target in $TargetDirs) {
        # Windows 的 Copy-Item 指定 -Recurse 且源路径不加通配符时，会自动保持文件夹本身外壳
        Copy-Item -Path $dir.FullName -Destination $target -Recurse -Force
    }
}

Write-Host "--------------------------------------------------" -ForegroundColor Cyan
Write-Host "🎉 完美搞定！Windows 环境下同步已全部完成。" -ForegroundColor Green