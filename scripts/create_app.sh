#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <app_name>" >&2
    exit 1
fi

app_name=$1

case "$app_name" in
    "" | [0-9]* | _* | *_ | *__* | *[!a-z0-9_]*)
        echo "App name must use lower snake_case and start with a letter" >&2
        exit 1
        ;;
esac

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_directory=$(dirname -- "$script_directory")
backend_directory="$repository_directory/backend"
destination="$backend_directory/apps/$app_name"

if [ -e "$destination" ]; then
    echo "App already exists: $destination" >&2
    exit 1
fi

cd "$backend_directory"
uv run --locked python manage.py startapp \
    --template "$script_directory/templates/django_app" \
    "$app_name" \
    "apps/$app_name"

echo "Created apps.$app_name"
echo "Add \"apps.$app_name\" to INSTALLED_APPS."
