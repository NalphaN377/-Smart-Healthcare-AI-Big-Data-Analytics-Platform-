"""pytest 根级配置：确保项目根目录在 sys.path 中，使 `import app` / `import config` 可用。

放在项目根目录，pytest 会自动将其所在目录加入 sys.path。
"""
