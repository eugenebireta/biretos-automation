#!/usr/bin/env python3
"""
Утилита для генерации X-Ray конфигов из шаблонов с подстановкой переменных окружения.
"""
import json
import os
import re
from pathlib import Path
from typing import Dict, Any


def load_env(env_file: Path) -> Dict[str, str]:
    """Загружает переменные из .env файла."""
    env = {}
    if not env_file.exists():
        return env
    
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                env[key.strip()] = value.strip()
    
    return env


def get_env_vars(base_dir: Path) -> Dict[str, str]:
    """Получает переменные окружения из .env и системных переменных."""
    env_file = base_dir / '.env'
    env = load_env(env_file)
    
    # Переопределяем системными переменными (если есть)
    for key in env.keys():
        sys_value = os.getenv(key)
        if sys_value:
            env[key] = sys_value
    
    # Добавляем системные переменные, которых нет в .env
    relevant_keys = [
        'XRAY_VPS_IP', 'XRAY_VPS_PORT', 'XRAY_VLESS_UUID',
        'PROXY_SOCKS5_PORT', 'PROXY_SOCKS5_HOST'
    ]
    for key in relevant_keys:
        if key not in env:
            sys_value = os.getenv(key)
            if sys_value:
                env[key] = sys_value
    
    return env


def render_template(template_path: Path, env: Dict[str, str]) -> Dict[str, Any]:
    """Рендерит JSON шаблон с подстановкой переменных."""
    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Заменяем {{VAR}} на значения из env
    def replace_var(match):
        var_name = match.group(1)
        value = env.get(var_name, match.group(0))
        # Если значение - число, возвращаем как число, иначе как строку
        try:
            return str(int(value))
        except ValueError:
            try:
                return str(float(value))
            except ValueError:
                return f'"{value}"'
    
    # Заменяем {{VAR}} на значения
    content = re.sub(r'\{\{(\w+)\}\}', replace_var, content)
    
    # Парсим JSON
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON after template rendering: {e}")


def render_xray_configs(base_dir: Path, output_dir: Path) -> Dict[str, Path]:
    """Рендерит все X-Ray конфиги из шаблонов."""
    configs_dir = base_dir / 'configs'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    env = get_env_vars(base_dir)
    
    # Проверяем обязательные переменные
    required_vars = ['XRAY_VPS_IP', 'XRAY_VPS_PORT', 'XRAY_VLESS_UUID', 'PROXY_SOCKS5_PORT']
    missing = [v for v in required_vars if v not in env]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    
    rendered = {}
    
    templates = [
        ('xray-client-usa.json.template', 'xray-client-usa.json'),
        ('xray-client-off.json.template', 'xray-client-off.json'),
        ('xray-server-usa.json.template', 'xray-server-usa.json'),
    ]
    
    for template_name, output_name in templates:
        template_path = configs_dir / template_name
        if not template_path.exists():
            continue
        
        config = render_template(template_path, env)
        output_path = output_dir / output_name
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        rendered[output_name] = output_path
    
    return rendered


if __name__ == '__main__':
    import sys
    
    base_dir = Path(__file__).parent.parent
    output_dir = base_dir / '.runtime'
    
    try:
        rendered = render_xray_configs(base_dir, output_dir)
        print(f"Rendered {len(rendered)} configs to {output_dir.resolve()}")
        for name, path in rendered.items():
            print(f"  - {name}: {path.resolve()}")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
