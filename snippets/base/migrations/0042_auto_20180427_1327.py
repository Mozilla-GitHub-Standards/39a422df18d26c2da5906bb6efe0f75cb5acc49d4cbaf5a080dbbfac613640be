# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations

from django_mysql.models.functions import AsType, ColumnAdd


def set_default_bounds_for_bookmarks_count(apps, schema_editor):
    Snippet = apps.get_model('base', 'Snippet')
    Snippet.objects.update(
        client_options=ColumnAdd('client_options',
                                 {'bookmarks_count_lower_bound': AsType(-1, 'INTEGER')})
    )
    Snippet.objects.update(
        client_options=ColumnAdd('client_options',
                                 {'bookmarks_count_upper_bound': AsType(-1, 'INTEGER')})
    )


def noop(apps, schema_editor):
    # nothing needed to go back in time.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0041_snippettemplate_startpage'),
    ]

    operations = [
        migrations.RunPython(set_default_bounds_for_bookmarks_count, noop)
    ]
