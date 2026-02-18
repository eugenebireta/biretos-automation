# Скрипт для настройки SSH-ключа на RU VPS
# Запускать один раз для настройки автоматического подключения

$RUVPS = "77.233.222.214"
$RUVPS_USER = "root"
$RUVPS_PASSWORD = "HuPtNj39"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  НАСТРОЙКА SSH-КЛЮЧА" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Проверка наличия ключа
$KEY_PATH = "$env:USERPROFILE\.ssh\id_ed25519.pub"
if (-not (Test-Path $KEY_PATH)) {
    Write-Host "[ERROR] SSH-ключ не найден: $KEY_PATH" -ForegroundColor Red
    Write-Host "Создаю новый ключ..." -ForegroundColor Yellow
    ssh-keygen -t ed25519 -C "biretos-automation" -f "$env:USERPROFILE\.ssh\id_ed25519" -N '""'
}

$PUBKEY = Get-Content $KEY_PATH
Write-Host "[1/3] Публичный ключ найден" -ForegroundColor Green
Write-Host "   $PUBKEY" -ForegroundColor Gray
Write-Host ""

# Копирование ключа на сервер
Write-Host "[2/3] Копирование ключа на сервер..." -ForegroundColor Yellow
Write-Host "   Сервер: $RUVPS_USER@$RUVPS" -ForegroundColor Cyan
Write-Host "   Потребуется ввести пароль один раз" -ForegroundColor Yellow
Write-Host ""

# Метод 1: Использование ssh-copy-id (если доступен)
if (Get-Command ssh-copy-id -ErrorAction SilentlyContinue) {
    Write-Host "   Используется ssh-copy-id..." -ForegroundColor Cyan
    $env:SSH_ASKPASS_REQUIRE = "never"
    echo $RUVPS_PASSWORD | ssh-copy-id -f -o StrictHostKeyChecking=no "$RUVPS_USER@$RUVPS"
} else {
    # Метод 2: Ручное добавление через ssh
    Write-Host "   Добавление ключа вручную..." -ForegroundColor Cyan
    
    # Создаем команду для добавления ключа
    $ADD_KEY_CMD = @"
mkdir -p ~/.ssh && chmod 700 ~/.ssh && 
echo '$PUBKEY' >> ~/.ssh/authorized_keys && 
chmod 600 ~/.ssh/authorized_keys && 
echo 'KEY_ADDED'
"@
    
    # Выполняем через ssh (потребуется ввести пароль)
    Write-Host "   Выполните вручную следующую команду:" -ForegroundColor Yellow
    Write-Host "   ssh $RUVPS_USER@$RUVPS `"$ADD_KEY_CMD`"" -ForegroundColor White
    Write-Host ""
    Write-Host "   Или скопируйте ключ вручную:" -ForegroundColor Yellow
    Write-Host "   type $KEY_PATH | ssh $RUVPS_USER@$RUVPS `"mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys`"" -ForegroundColor White
}

Write-Host ""
Write-Host "[3/3] Проверка подключения..." -ForegroundColor Yellow

# Тест подключения
$TEST_RESULT = ssh -o BatchMode=yes -o ConnectTimeout=5 "$RUVPS_USER@$RUVPS" "echo 'SSH_KEY_WORKS'" 2>&1

if ($TEST_RESULT -match "SSH_KEY_WORKS") {
    Write-Host "   [OK] SSH-ключ настроен успешно!" -ForegroundColor Green
    Write-Host "   Теперь можно подключаться без пароля" -ForegroundColor Green
} else {
    Write-Host "   [WARNING] Автоматическая проверка не удалась" -ForegroundColor Yellow
    Write-Host "   Проверьте вручную: ssh $RUVPS_USER@$RUVPS" -ForegroundColor White
    Write-Host "   Если запрашивается пароль - ключ не скопирован" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan

