<?php
/**
 * Local configuration for the legacy CRBS app when it runs from docker compose (profile "legacy").
 * Mounted at /var/www/html/local/config.php; values come from the container environment.
 * See crbs-core/application/config/database.php (local/config.php is merged into $db['default']).
 */
return [
    'database' => [
        'hostname' => getenv('CRBS_DB_HOST') ?: 'crbs-db',
        'username' => getenv('CRBS_DB_USER') ?: 'crbs',
        'password' => getenv('CRBS_DB_PASSWORD') ?: '',
        'database' => getenv('CRBS_DB_NAME') ?: 'crbs',
        'dbdriver' => 'mysqli',
    ],
];
