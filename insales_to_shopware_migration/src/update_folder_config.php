<?php
// Скрипт для обновления configurationId папки через SQL
require __DIR__ . '/../../../../vendor/autoload.php';

use Shopware\Core\Framework\Context;
use Shopware\Core\Framework\DataAbstractionLayer\EntityRepository;
use Symfony\Component\DependencyInjection\ContainerInterface;

$folderId = '01994d23ada87207aa7d8cb9994f5198';
$configId = '8c63f6b3940441929cff2ef6dd9f7aa3';

// Преобразуем UUID в HEX (без дефисов)
$folderIdHex = str_replace('-', '', $folderId);
$configIdHex = str_replace('-', '', $configId);

$sql = "UPDATE media_folder SET configuration_id = UNHEX('$configIdHex') WHERE id = UNHEX('$folderIdHex');";

echo "SQL команда:\n";
echo $sql . "\n\n";
echo "Выполните эту команду в MySQL:\n";
echo "mysql -u root -p shopware -e \"$sql\"\n";




