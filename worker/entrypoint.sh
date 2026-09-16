#!/bin/sh
set -eu
exec celery -A app.worker.celery_app worker --loglevel=INFO --queues=cad_tasks --concurrency=1 --hostname=cad@%h
