#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from django.conf import settings
from django.contrib.postgres.fields import JSONField, ArrayField
from django.db import migrations, models
from django.utils.timezone import now

import uuid
import mptt.fields
import bridge.utils
import reports.models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('jobs', '0001_initial'),
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [

        migrations.CreateModel(name='ReportRoot', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('resources', JSONField(default=dict)),
            ('instances', JSONField(default=dict)),
            ('job', models.OneToOneField(on_delete=models.deletion.CASCADE, to='jobs.Job')),
            ('user', models.ForeignKey(
                null=True, on_delete=models.deletion.SET_NULL, related_name='roots', to=settings.AUTH_USER_MODEL
            )),
        ], options={'db_table': 'report_root'}),

        migrations.CreateModel(name='AdditionalSources', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('archive', models.FileField(upload_to='Sources/%Y/%m')),
            ('root', models.ForeignKey(on_delete=models.deletion.CASCADE, to='reports.ReportRoot')),
        ], options={'db_table': 'report_additional_sources'}, bases=(bridge.utils.WithFilesMixin, models.Model)),

        migrations.CreateModel(name='AttrFile', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('file', models.FileField(upload_to=reports.models.get_attr_data_path)),
            ('root', models.ForeignKey(on_delete=models.deletion.CASCADE, to='reports.ReportRoot')),
        ], options={'db_table': 'report_attr_file'}, bases=(bridge.utils.WithFilesMixin, models.Model)),

        migrations.CreateModel(name='CompareJobsInfo', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('names', ArrayField(base_field=models.CharField(max_length=64), size=None)),
            ('root1', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='+', to='reports.ReportRoot')),
            ('root2', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='+', to='reports.ReportRoot')),
            ('user', models.ForeignKey(on_delete=models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ], options={'db_table': 'cache_report_jobs_compare_info'}),

        migrations.CreateModel(name='ComparisonObject', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('values', ArrayField(base_field=models.CharField(max_length=255), size=None)),
            ('verdict1', models.CharField(choices=[
                ('0', 'Total safe'), ('1', 'Found all unsafes'), ('2', 'Found not all unsafes'),
                ('3', 'Unknown'), ('4', 'Unmatched'), ('5', 'Broken')
            ], max_length=1)),
            ('verdict2', models.CharField(choices=[
                ('0', 'Total safe'), ('1', 'Found all unsafes'), ('2', 'Found not all unsafes'),
                ('3', 'Unknown'), ('4', 'Unmatched'), ('5', 'Broken')
            ], max_length=1)),
            ('info', models.ForeignKey(on_delete=models.deletion.CASCADE, to='reports.CompareJobsInfo')),
        ], options={'db_table': 'cache_report_comparison_object'}),

        migrations.CreateModel(name='ComparisonLink', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('object_id', models.PositiveIntegerField()),
            ('comparison', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='links', to='reports.ComparisonObject'
            )),
            ('content_type', models.ForeignKey(on_delete=models.deletion.CASCADE, to='contenttypes.ContentType')),
        ], options={'db_table': 'cache_report_comparison_link'}),

        migrations.CreateModel(name='Computer', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('identifier', models.CharField(db_index=True, max_length=128)),
            ('display', models.CharField(max_length=512)),
            ('data', JSONField()),
        ], options={'db_table': 'computer'}),

        migrations.CreateModel(name='OriginalSources', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('identifier', models.CharField(db_index=True, max_length=128, unique=True)),
            ('archive', models.FileField(upload_to='OriginalSources')),
        ], options={
            'db_table': 'report_original_sources',
            'ordering': ('identifier',)
        }, bases=(bridge.utils.WithFilesMixin, models.Model)),

        migrations.CreateModel(name='Report', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('identifier', models.CharField(db_index=True, max_length=255)),
            ('cpu_time', models.BigIntegerField(null=True)),
            ('wall_time', models.BigIntegerField(null=True)),
            ('memory', models.BigIntegerField(null=True)),
            ('lft', models.PositiveIntegerField(db_index=True, editable=False)),
            ('rght', models.PositiveIntegerField(db_index=True, editable=False)),
            ('tree_id', models.PositiveIntegerField(db_index=True, editable=False)),
            ('level', models.PositiveIntegerField(db_index=True, editable=False)),
            ('root', models.ForeignKey(on_delete=models.deletion.CASCADE, to='reports.ReportRoot')),
        ], options={'db_table': 'report'}),

        migrations.CreateModel(name='ReportAttr', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('name', models.CharField(db_index=True, max_length=64)),
            ('value', models.CharField(max_length=255)),
            ('compare', models.BooleanField(default=False)),
            ('associate', models.BooleanField(default=False)),
            ('data', models.ForeignKey(null=True, on_delete=models.deletion.CASCADE, to='reports.AttrFile')),
            ('report', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='attrs', to='reports.Report')),
        ], options={'db_table': 'report_attrs'}),

        migrations.CreateModel(name='ReportComponent', fields=[
            ('report_ptr', models.OneToOneField(
                auto_created=True, on_delete=models.deletion.CASCADE, parent_link=True,
                primary_key=True, serialize=False, to='reports.Report'
            )),
            ('component', models.CharField(max_length=20)),
            ('verification', models.BooleanField(default=False)),
            ('start_date', models.DateTimeField(default=now)),
            ('finish_date', models.DateTimeField(null=True)),
            ('data', JSONField(null=True)),
            ('log', models.FileField(null=True, upload_to=reports.models.get_component_path)),
            ('verifier_input', models.FileField(null=True, upload_to=reports.models.get_component_path)),
            ('additional', models.ForeignKey(
                null=True, on_delete=models.deletion.CASCADE, to='reports.AdditionalSources'
            )),
            ('computer', models.ForeignKey(on_delete=models.deletion.CASCADE, to='reports.Computer')),
            ('original', models.ForeignKey(null=True, on_delete=models.deletion.PROTECT, to='reports.OriginalSources')),
        ], options={'db_table': 'report_component'}, bases=(bridge.utils.WithFilesMixin, 'reports.report')),

        migrations.CreateModel(name='CoverageArchive', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('identifier', models.CharField(default='', max_length=128)),
            ('archive', models.FileField(upload_to=reports.models.get_coverage_arch_dir)),
            ('report', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='coverages', to='reports.ReportComponent'
            )),
        ], options={'db_table': 'report_coverage_archive'}, bases=(bridge.utils.WithFilesMixin, models.Model)),

        migrations.CreateModel(name='ReportComponentLeaf', fields=[
            ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('object_id', models.PositiveIntegerField()),
            ('content_type', models.ForeignKey(on_delete=models.deletion.CASCADE, to='contenttypes.ContentType')),
            ('report', models.ForeignKey(
                on_delete=models.deletion.CASCADE, related_name='leaves', to='reports.ReportComponent'
            )),
        ], options={'db_table': 'cache_report_component_leaf'}),

        migrations.CreateModel(name='ReportSafe', fields=[
            ('report_ptr', models.OneToOneField(
                auto_created=True, on_delete=models.deletion.CASCADE, parent_link=True,
                primary_key=True, serialize=False, to='reports.Report'
            )),
            ('proof', models.FileField(null=True, upload_to='Safes/%Y/%m')),
        ], options={'db_table': 'report_safe'}, bases=(bridge.utils.WithFilesMixin, 'reports.report')),

        migrations.CreateModel(name='ReportUnknown', fields=[
            ('report_ptr', models.OneToOneField(
                auto_created=True, on_delete=models.deletion.CASCADE, parent_link=True,
                primary_key=True, serialize=False, to='reports.Report'
            )),
            ('component', models.CharField(max_length=20)),
            ('problem_description', models.FileField(upload_to='Unknowns/%Y/%m')),
        ], options={'db_table': 'report_unknown'}, bases=(bridge.utils.WithFilesMixin, 'reports.report')),

        migrations.CreateModel(name='ReportUnsafe', fields=[
            ('report_ptr', models.OneToOneField(
                auto_created=True, on_delete=models.deletion.CASCADE, parent_link=True,
                primary_key=True, serialize=False, to='reports.Report'
            )),
            ('trace_id', models.UUIDField(db_index=True, default=uuid.uuid4, unique=True)),
            ('error_trace', models.FileField(upload_to='Unsafes/%Y/%m')),
        ], options={'db_table': 'report_unsafe'}, bases=(bridge.utils.WithFilesMixin, 'reports.report')),

        migrations.AddField(model_name='report', name='parent', field=mptt.fields.TreeForeignKey(
            null=True, on_delete=models.deletion.CASCADE, related_name='children', to='reports.Report')
        ),

        migrations.AddIndex(
            model_name='reportattr', index=models.Index(fields=['name', 'value'], name='report_attr_name_e431b9_idx'),
        ),
        migrations.AlterUniqueTogether(name='report', unique_together={('root', 'identifier')}),
        migrations.AlterIndexTogether(name='report', index_together={('root', 'identifier')}),
        migrations.AlterIndexTogether(name='comparisonobject', index_together={('info', 'verdict1', 'verdict2')}),

    ]
