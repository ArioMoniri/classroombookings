# syntax=docker/dockerfile:1.7
# Legacy classroombookings (CRBS, CodeIgniter 3) served by Apache so the live app can be
# imported into SmartSched (`python -m app.cli import crbs --dsn mysql://…`).
# Build context: the repository root (set in docker-compose.yml, profile "legacy").
FROM php:8.3-apache
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends libicu-dev libzip-dev zlib1g-dev; \
    docker-php-ext-install -j"$(nproc)" mysqli pdo_mysql intl zip; \
    apt-get purge -y --auto-remove libicu-dev libzip-dev zlib1g-dev; \
    apt-get install -y --no-install-recommends libicu72 libzip4; \
    rm -rf /var/lib/apt/lists/*; \
    a2enmod rewrite headers; \
    mv "$PHP_INI_DIR/php.ini-production" "$PHP_INI_DIR/php.ini"; \
    sed -i 's/^upload_max_filesize.*/upload_max_filesize = 50M/; s/^post_max_size.*/post_max_size = 50M/' "$PHP_INI_DIR/php.ini"
# CodeIgniter front-controller rewrite (mirrors .htaccess.txt at the repo root).
COPY smartsched/deploy/legacy/apache-crbs.conf /etc/apache2/conf-enabled/zz-crbs.conf
# The app itself is bind-mounted at run time (see docker-compose.yml) so no code is baked in;
# `local/` must be writable by www-data (cache, sessions, logs).
WORKDIR /var/www/html
