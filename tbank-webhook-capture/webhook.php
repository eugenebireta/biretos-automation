<?php
// tbank-webhook-capture.php
// Временный receiver v0.1 для получения payload от Т-Банка
// УДАЛИТЬ после получения реального payload

// 1. HTTP Method Guard
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    header('Content-Type: application/json');
    echo json_encode(['error' => 'Method not allowed']);
    exit;
}

header('Content-Type: application/json');
http_response_code(200);

// 3. Headers совместимость
if (function_exists('getallheaders')) {
    $headers = getallheaders();
} else {
    // Fallback: сбор headers из $_SERVER
    $headers = [];
    foreach ($_SERVER as $key => $value) {
        if (strpos($key, 'HTTP_') === 0) {
            $headerName = str_replace(' ', '-', ucwords(str_replace('_', ' ', strtolower(substr($key, 5)))));
            $headers[$headerName] = $value;
        }
    }
}

// Получение данных
$body = file_get_contents('php://input');
$timestamp = date('c'); // ISO 8601

// Парсинг body (если JSON)
$bodyParsed = null;
if (!empty($body)) {
    $bodyParsed = json_decode($body, true);
}

// Подготовка лога
$logEntry = [
    'timestamp' => $timestamp,
    'headers' => $headers,
    'body' => $bodyParsed !== null ? $bodyParsed : null,
    'raw_body' => $body,
    'method' => $_SERVER['REQUEST_METHOD'],
    'uri' => $_SERVER['REQUEST_URI'] ?? '',
    'remote_addr' => $_SERVER['REMOTE_ADDR'] ?? 'unknown'
];

// 2. Fail-safe логирование
$logDir = '/var/log/tbank-webhook-capture/';
$logEntryJson = json_encode($logEntry, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT) . "\n";

// Попытка записи в файл
$written = false;
if (is_dir($logDir) || @mkdir($logDir, 0755, true)) {
    $logFile = $logDir . 'payload_' . date('Y-m-d') . '.jsonl';
    $written = @file_put_contents($logFile, $logEntryJson, FILE_APPEND | LOCK_EX);
}

// Fallback на error_log если запись не удалась
if ($written === false) {
    error_log('[TBANK-WEBHOOK] Failed to write log file, using error_log: ' . $logEntryJson);
}

// Ответ
echo json_encode(['status' => 'ok', 'received_at' => $timestamp]);
?>








