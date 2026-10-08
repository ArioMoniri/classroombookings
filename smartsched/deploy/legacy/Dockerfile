# syntax=docker/dockerfile:1.7
# Legacy classroombookings (CRBS, CodeIgniter 3; needs mysqli + intl) served by Apache, so the live app
# can run next to SmartSched and be imported (`python -m app.cli import crbs --dsn mysql://...`).
#
# Build context: the repository root (docker-compose.yml, profile "legacy"). Only the PHP app is copied
# (see Dockerfile.dockerignore next to this file); smartsched/, docs/, .git and secrets never enter the image.
# Runs as www-data (non-root) on port 8080. local/ and uploads/ are named volumes in compose so the
# install marker, sessions, logs and uploaded files survive image upgrades.

ARG PHP_IMAGE=php:8.3.35-apache-bookworm
FROM ${PHP_IMAGE}

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends libicu-dev; \
    docker-php-ext-install -j"$(nproc)" mysqli pdo_mysql intl; \
    apt-get purge -y --auto-remove libicu-dev; \
    apt-get install -y --no-install-recommends libicu72; \
    rm -rf /var/lib/apt/lists/*; \
    a2enmod rewrite headers; \
    mv "$PHP_INI_DIR/php.ini-production" "$PHP_INI_DIR/php.ini"; \
    sed -i 's/^upload_max_filesize.*/upload_max_filesize = 50M/; s/^post_max_size.*/post_max_size = 50M/; s/^expose_php.*/expose_php = Off/' "$PHP_INI_DIR/php.ini"; \
    # non-root: Apache cannot bind :80 as www-data, so listen on 8080
    sed -i 's/^Listen 80$/Listen 8080/' /etc/apache2/ports.conf; \
    sed -i 's/<VirtualHost \*:80>/<VirtualHost *:8080>/' /etc/apache2/sites-available/000-default.conf; \
    echo 'ServerName localhost' > /etc/apache2/conf-enabled/zz-servername.conf; \
    echo 'ServerTokens Prod' >> /etc/apache2/conf-enabled/zz-servername.conf; \
    echo 'ServerSignature Off' >> /etc/apache2/conf-enabled/zz-servername.conf

# CodeIgniter front-controller rewrite (mirrors .htaccess.txt at the repo root) + deny internal dirs.
COPY smartsched/deploy/legacy/apache-crbs.conf /etc/apache2/conf-enabled/zz-crbs.conf

WORKDIR /var/www/html
COPY --chown=root:root index.php ./
COPY --chown=root:root assets ./assets
COPY --chown=root:root crbs-core ./crbs-core
COPY --chown=www-data:www-data local ./local
COPY --chown=www-data:www-data uploads ./uploads
# DB settings from the container environment (CRBS merges local/config.php into $db['default']).
COPY --chown=www-data:www-data smartsched/deploy/legacy/config.php ./local/config.php
RUN set -eux; \
    mkdir -p local/cache local/sessions local/logs; \
    chown -R www-data:www-data local uploads

USER www-data
EXPOSE 8080
HEALTHCHECK --interval=20s --timeout=5s --start-period=20s --retries=5 \
  CMD curl -fsS -o /dev/null http://127.0.0.1:8080/ || exit 1
