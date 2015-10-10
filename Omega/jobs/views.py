import os
import json
import pytz
import mimetypes
from io import BytesIO
from urllib.parse import quote
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.utils.translation import ugettext as _, activate
from django.core.exceptions import MultipleObjectsReturned
from Omega.vars import VIEW_TYPES
from jobs.forms import FileForm
from jobs.ViewJobData import ViewJobData
from jobs.JobTableProperties import FilterForm, TableTree
from users.models import View, PreferableView
from reports.UploadReport import UploadReport
from reports.models import ReportComponent
from jobs.Download import UploadJob, DownloadJob, PSIDownloadJob, DownloadLock
from jobs.utils import *
from reports.models import ReportRoot


@login_required
def tree_view(request):
    activate(request.user.extended.language)

    tree_args = [request.user]
    if request.method == 'POST':
        tree_args.append(request.POST.get('view', None))
        tree_args.append(request.POST.get('view_id', None))

    return render(request, 'jobs/tree.html', {
        'FF': FilterForm(*tree_args),
        'users': User.objects.all(),
        'statuses': JOB_STATUS,
        'can_create': JobAccess(request.user).can_create(),
        'TableData': TableTree(*tree_args)
    })


@login_required
def preferable_view(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'status': 1, 'message': _("Unknown error")})

    view_id = request.POST.get('view_id', None)
    view_type = request.POST.get('view_type', None)
    if view_id is None or view_type is None:
        return JsonResponse({'status': 1, 'message': _("Unknown error")})

    if view_id == 'default':
        pref_views = request.user.preferableview_set.filter(
            view__type=view_type)
        if len(pref_views):
            pref_views.delete()
            return JsonResponse({
                'status': 0,
                'message': _("The default view was made preferred")
            })
        return JsonResponse({
            'status': 1,
            'message': _("The default view is already preferred")
        })

    try:
        user_view = View.objects.get(pk=int(view_id),
                                     author=request.user, type=view_type)
    except ObjectDoesNotExist:
        return JsonResponse({
            'status': 1,
            'message': _("The view was not found")
        })
    request.user.preferableview_set.filter(view__type=view_type).delete()
    pref_view = PreferableView()
    pref_view.user = request.user
    pref_view.view = user_view
    pref_view.save()
    return JsonResponse({
        'status': 0,
        'message': _("The preferred view was successfully changed")
    })


@login_required
def check_view_name(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return JsonResponse({'status': False, 'message': _('Unknown error')})

    view_name = request.POST.get('view_title', None)
    view_type = request.POST.get('view_type', None)
    if view_name is None or view_type is None:
        return JsonResponse({'status': False, 'message': _('Unknown error')})

    if view_name == _('Default'):
        return JsonResponse({
            'status': False, 'message': _("Please choose another view name")
        })

    if view_name == '':
        return JsonResponse({
            'status': False, 'message': _("The view name is required")
        })

    if len(request.user.view_set.filter(type=view_type, name=view_name)):
        return JsonResponse({
            'status': False, 'message': _("Please choose another view name")
        })
    return JsonResponse({'status': True})


@login_required
def save_view(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'status': 1, 'message': _('Unknown error')})

    view_data = request.POST.get('view', None)
    view_name = request.POST.get('title', '')
    view_id = request.POST.get('view_id', None)
    view_type = request.POST.get('view_type', None)
    if view_data is None or view_type is None or \
            view_type not in list(x[0] for x in VIEW_TYPES):
        return JsonResponse({'status': 1, 'message': _('Unknown error')})
    if view_id == 'default':
        return JsonResponse({
            'status': 1,
            'message': _("You can't edit the default view")
        })
    elif view_id is not None:
        try:
            new_view = request.user.view_set.get(pk=int(view_id))
        except ObjectDoesNotExist:
            return JsonResponse({
                'status': 1,
                'message': _('The view was not found')
            })
    elif len(view_name):
        new_view = View()
        new_view.name = view_name
        new_view.type = view_type
        new_view.author = request.user
    else:
        return JsonResponse({
            'status': 1, 'message': _('The view name is required')
        })
    new_view.view = view_data
    new_view.save()
    return JsonResponse({
        'status': 0,
        'view_id': new_view.pk,
        'view_name': new_view.name,
        'message': _("The view was successfully saved")
    })


@login_required
def remove_view(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'status': 1, 'message': _("Unknown error")})
    v_id = request.POST.get('view_id', 0)
    view_type = request.POST.get('view_type', None)
    if view_type is None:
        return JsonResponse({'status': 1, 'message': _("Unknown error")})
    if v_id == 'default':
        return JsonResponse({
            'status': 1,
            'message': _("You can't remove the default view")
        })
    try:
        View.objects.get(
            author=request.user, pk=int(v_id), type=view_type
        ).delete()
    except ObjectDoesNotExist:
        return JsonResponse({
            'status': 1,
            'message': _("The view was not found")
        })
    return JsonResponse({
        'status': 0,
        'message': _("The view was successfully removed")
    })


@login_required
def show_job(request, job_id=None):
    activate(request.user.extended.language)

    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[404]))

    job_access = JobAccess(request.user, job)
    if not job_access.can_view():
        return HttpResponseRedirect(reverse('error', args=[400]))

    parent_set = []
    next_parent = job.parent
    while next_parent is not None:
        parent_set.append(next_parent)
        next_parent = next_parent.parent
    parent_set.reverse()
    parents = []
    for parent in parent_set:
        if JobAccess(request.user, parent).can_view():
            job_id = parent.pk
        else:
            job_id = None
        parents.append({
            'pk': job_id,
            'name': parent.name,
        })

    children = []
    for child in job.children.all():
        if JobAccess(request.user, child).can_view():
            job_id = child.pk
        else:
            job_id = None
        children.append({
            'pk': job_id,
            'name': child.name,
        })

    reportdata = None
    try:
        report = ReportComponent.objects.get(root__job=job, parent=None)
        view_args = [request.user, report]
        if request.method == 'POST':
            view_args.append(request.POST.get('view', None))
            view_args.append(request.POST.get('view_id', None))
        reportdata = ViewJobData(*view_args)
    except ObjectDoesNotExist:
        pass

    return render(
        request,
        'jobs/viewJob.html',
        {
            'job': job,
            'comment': job.versions.get(version=job.version).comment,
            'parents': parents,
            'children': children,
            'reportdata': reportdata,
            'created_by': job.versions.get(version=1).change_author,
            'can_delete': job_access.can_delete(),
            'can_edit': job_access.can_edit(),
            'can_create': job_access.can_create(),
            'can_decide': job_access.can_decide(),
            'schedulers': get_available_schedulers(request.user)
        }
    )


@login_required
def edit_job(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return HttpResponse('')

    job_id = request.POST.get('job_id', 0)

    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return HttpResponse('')
    if not JobAccess(request.user, job).can_edit():
        return HttpResponse('')

    version = int(request.POST.get('version', 0))
    if version > 0:
        job_version = job.versions.get(version=version)
    else:
        job_version = job.versions.order_by('-change_date')[0]

    job_versions = []
    for j in job.versions.order_by('-version'):
        if j.version == job.version:
            title = _("Current version")
        else:
            job_time = j.change_date.astimezone(
                pytz.timezone(request.user.extended.timezone)
            )
            title = job_time.strftime("%d.%m.%Y %H:%M:%S")
            title += " (%s %s)" % (
                j.change_author.extended.last_name,
                j.change_author.extended.first_name,
            )
            title += ': ' + j.comment
        job_versions.append({
            'version': j.version,
            'title': title
        })

    parent_identifier = None
    if job_version.parent is not None:
        parent_identifier = job_version.parent.identifier

    return render(request, 'jobs/editJob.html', {
        'parent_id': parent_identifier,
        'job': job_version,
        'job_id': job_id,
        'roles': role_info(job_version, request.user),
        'job_roles': JOB_ROLES,
        'job_versions': job_versions,
        'version': version,
        'filedata': FileData(job_version).filedata
    })


@login_required
def remove_versions(request):
    if request.method != 'POST':
        return JsonResponse({'status': 1, 'message': _('Unknown error')})
    job_id = int(request.POST.get('job_id', 0))
    try:
        job = Job.objects.get(pk=job_id)
    except ObjectDoesNotExist:
        return JsonResponse({
            'status': 1, 'message': _('The job was not found')
        })
    if not JobAccess(request.user, job).can_edit():
        return JsonResponse({
            'status': 1,
            'message': _("You don't have access to delete versions")
        })

    versions = json.loads(request.POST.get('versions', '[]'))

    deleted_versions = delete_versions(job, versions)
    if deleted_versions > 0:
        return JsonResponse({
            'status': 0,
            'message': _('Selected versions were successfully deleted')
        })
    return JsonResponse({'status': 1, 'message': _('Nothing to delete')})


@login_required
def get_job_versions(request):
    if request.method != 'POST':
        return JsonResponse({'message': _('Unknown error')})
    job_id = int(request.POST.get('job_id', 0))
    try:
        job = Job.objects.get(pk=job_id)
    except ObjectDoesNotExist:
        return JsonResponse({'message': _('The job was not found')})
    job_versions = []
    for j in job.versions.filter(
            ~Q(version__in=[job.version, 1])).order_by('-version'):
        job_time = j.change_date.astimezone(
            pytz.timezone(request.user.extended.timezone)
        )
        title = job_time.strftime("%d.%m.%Y %H:%M:%S")
        title += " (%s %s)" % (
            j.change_author.extended.last_name,
            j.change_author.extended.first_name,
        )
        title += ': ' + j.comment
        job_versions.append({
            'version': j.version,
            'title': title
        })
    return render(request, 'jobs/viewVersions.html', {'versions': job_versions})


@login_required
def copy_new_job(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return HttpResponse('')
    if not JobAccess(request.user).can_create():
        return HttpResponse('')

    roles = {
        'user_roles': [],
        'global': JOB_ROLES[0][0],
        'available_users': []
    }
    for u in User.objects.filter(~Q(pk=request.user.pk)):
        roles['available_users'].append({
            'id': u.pk,
            'name': u.extended.last_name + ' ' + u.extended.first_name
        })

    job = get_object_or_404(Job, pk=int(request.POST.get('parent_id', 0)))
    job_version = job.versions.order_by('-change_date')[0]

    return render(request, 'jobs/createJob.html', {
        'parent_id': job.identifier,
        'job': job_version,
        'roles': roles,
        'job_roles': JOB_ROLES,
        'filedata': FileData(job_version).filedata
    })


@login_required
def save_job(request):
    if request.method != 'POST':
        return JsonResponse({'status': 1, 'message': _('Unknown error')})

    job_kwargs = {
        'name': request.POST.get('title', ''),
        'description': request.POST.get('description', ''),
        'global_role': request.POST.get('global_role', JOB_ROLES[0][0]),
        'user_roles': json.loads(request.POST.get('user_roles', '[]')),
        'filedata': json.loads(request.POST.get('file_data', '[]')),
        'author': request.user
    }
    job_id = request.POST.get('job_id', None)
    parent_identifier = request.POST.get('parent_identifier', None)

    if job_id is not None:
        try:
            job = Job.objects.get(pk=int(job_id))
        except ObjectDoesNotExist:
            return JsonResponse({
                'status': 1,
                'message': _('The job was not found')
            })
        if not JobAccess(request.user, job).can_edit():
            return JsonResponse({
                'status': 1,
                'message': _("You don't have an access to edit this job")
            })
        if parent_identifier is not None and len(parent_identifier) > 0:
            parents = Job.objects.filter(
                identifier__startswith=parent_identifier
            )
            if len(parents) == 0:
                return JsonResponse({
                    'status': 1,
                    'message': _('The job parent was not found')
                })
            elif len(parents) > 1:
                return JsonResponse({
                    'status': 1,
                    'message': _('Several parents match the specified '
                                 'identifier, please increase the length '
                                 'of the parent identifier')
                })
            parent = parents[0]
            if job.parent is None:
                return JsonResponse({
                    'status': 1,
                    'message': _("Parent can't be specified for root jobs")
                })
            if not check_new_parent(job, parent):
                return JsonResponse({
                    'status': 1,
                    'message': _("The specified parent can't "
                                 "be set for this job")
                })
            job_kwargs['parent'] = parent
        elif job.parent is not None:
            return JsonResponse({
                'status': 1,
                'message': _("The parent identifier is required for this job")
            })
        if job.version != int(request.POST.get('last_version', 0)):
            return JsonResponse({
                'status': 1,
                'message': _("Your version is expired, please reload the page")
            })
        job_kwargs['job'] = job
        job_kwargs['comment'] = request.POST.get('comment', '')
        job_kwargs['absolute_url'] = 'http://' + request.get_host() + \
                                     reverse('jobs:job', args=[job_id])
        updated_job = update_job(job_kwargs)
        if isinstance(updated_job, Job):
            return JsonResponse({'status': 0, 'job_id': job.pk})
        else:
            return JsonResponse({'status': 1, 'message': updated_job + ''})
    elif parent_identifier is not None:
        try:
            parent = Job.objects.get(identifier=parent_identifier)
        except ObjectDoesNotExist:
            return JsonResponse({
                'status': 1,
                'message': _('The job parent was not found')
            })
        if not JobAccess(request.user).can_create():
            return JsonResponse({
                'status': 1,
                'message': _("You don't have an access to create new jobs")
            })
        job_kwargs['parent'] = parent
        job_kwargs['absolute_url'] = 'http://' + request.get_host()
        newjob = create_job(job_kwargs)
        if isinstance(newjob, Job):
            return JsonResponse({'status': 0, 'job_id': newjob.pk})
        return JsonResponse({'status': 1, 'message': newjob + ''})
    return JsonResponse({'status': 1, 'message': _('Unknown error')})


@login_required
def remove_jobs(request):
    activate(request.user.extended.language)

    if request.method != 'POST':
        return JsonResponse({'status': 1, 'message': _('Unknown error')})
    jobs_for_del = json.loads(request.POST.get('jobs', '[]'))
    status = remove_jobs_by_id(request.user, jobs_for_del)
    if status == 404:
        if len(jobs_for_del) == 1:
            return JsonResponse({
                'status': 1, 'message': _('The job was not found')
            })
        return JsonResponse({
            'status': 1,
            'message': _('One of the selected jobs was not found')
        })
    elif status == 400:
        if len(jobs_for_del) == 1:
            return JsonResponse({
                'status': 1,
                'message': _("You don't have an access to remove this job")
            })
        return JsonResponse({
            'status': 1,
            'message': _("You don't have an access to remove "
                         "one of the selected jobs")
        })
    return JsonResponse({'status': 0})


@login_required
def showjobdata(request):
    activate(request.user.extended.language)
    if request.method != 'POST':
        return HttpResponse('')
    try:
        job = Job.objects.get(pk=int(request.POST.get('job_id', 0)))
    except ObjectDoesNotExist:
        return HttpResponse('')

    return render(request, 'jobs/showJob.html', {
        'job': job,
        'description': job.versions.get(version=job.version).description,
        'filedata': FileData(job.versions.get(version=job.version)).filedata
    })


@login_required
def upload_file(request):
    if request.method != 'POST':
        return HttpResponse('')
    form = FileForm(request.POST, request.FILES)
    if form.is_valid():
        new_file = form.save(commit=False)
        hash_sum = hashlib.md5(new_file.file.read()).hexdigest()
        if len(File.objects.filter(hash_sum=hash_sum)) > 0:
            return JsonResponse({
                'hash_sum': hash_sum,
                'status': 0
            })
        new_file.hash_sum = hash_sum
        if not all(ord(c) < 128 for c in new_file.file.name):
            title_size = len(new_file.file.name)
            if title_size > 30:
                new_file.file.name = new_file.file.name[(title_size - 30):]
        new_file.save()
        return JsonResponse({
            'hash_sum': hash_sum,
            'status': 0
        })
    return JsonResponse({
        'message': _('File uploading failed'),
        'form_errors': form.errors,
        'status': 1
    })


@login_required
def download_file(request, file_id):
    if request.method == 'POST':
        return HttpResponse('')
    try:
        source = FileSystem.objects.get(pk=int(file_id))
    except ObjectDoesNotExist:
        return HttpResponse('')
    if source.file is None:
        return HttpResponse('')
    new_file = BytesIO(source.file.file.read())
    mimetype = mimetypes.guess_type(os.path.basename(source.file.file.name))[0]
    response = HttpResponse(new_file.read(), content_type=mimetype)
    response['Content-Disposition'] = 'attachment; filename="%s"' % source.name
    return response


@login_required
def download_job(request, job_id):
    if request.method == 'POST':
        return HttpResponse('')
    try:
        job = Job.objects.get(pk=int(job_id))
    except ObjectDoesNotExist:
        return HttpResponseRedirect(reverse('error', args=[404]))
    if not JobAccess(request.user, job).can_view():
        return HttpResponseRedirect(reverse('error', args=[400]))

    back_url = quote(reverse('jobs:job', args=[job_id]))
    hash_sum = request.GET.get('hashsum', None)
    if hash_sum is None:
        return HttpResponseRedirect(
            reverse('error', args=[451]) + "?back=%s" % back_url
        )
    jobtar = DownloadJob(job, hash_sum)

    if jobtar.error is not None:
        return HttpResponseRedirect(
            reverse('error', args=[500]) + "?back=%s" % back_url
        )
    response = HttpResponse(content_type="application/x-tar-gz")
    response["Content-Disposition"] = "attachment; filename=%s" % jobtar.tarname
    jobtar.memory.seek(0)
    response.write(jobtar.memory.read())
    return response


@login_required
def download_lock(request):
    tarlock = DownloadLock(user=request.user)
    status = tarlock.locked
    response_data = {'status': status}
    if status:
        response_data['hash_sum'] = tarlock.hash_sum
    return JsonResponse(response_data)


@login_required
def check_access(request):
    if request.method == 'POST':
        jobs = json.loads(request.POST.get('jobs', '[]'))
        for job_id in jobs:
            try:
                job = Job.objects.get(pk=int(job_id))
            except ObjectDoesNotExist:
                return JsonResponse({
                    'status': False,
                    'message': _('The job was not found')
                })
            if not JobAccess(request.user, job).can_view():
                return JsonResponse({
                    'status': False,
                    'message': _("You don't have an access to this job")
                })
        return JsonResponse({
            'status': True,
            'message': ''
        })


@login_required
def upload_job(request, parent_id=None):
    if len(parent_id) == 0:
        return JsonResponse({
            'status': False,
            'message': _("The parent identifier was not got")
        })
    parents = Job.objects.filter(identifier__startswith=parent_id)
    if len(parents) == 0:
        return JsonResponse({
            'status': False,
            'message': _("The parent with the specified "
                         "identifier was not found")
        })
    elif len(parents) > 1:
        return JsonResponse({
            'status': False,
            'message': _("Too many jobs starts with the specified identifier")
        })
    parent = parents[0]
    failed_jobs = []
    for f in request.FILES.getlist('file'):
        zipdata = UploadJob(parent, request.user, f)
        if zipdata.err_message is not None:
            failed_jobs.append([zipdata.err_message + '', f.name])
    if len(failed_jobs) > 0:
        return JsonResponse({
            'status': False,
            'messages': failed_jobs
        })
    return JsonResponse({
        'status': True
    })


def decide_job(request):
    if not request.user.is_authenticated():
        return JsonResponse({'error': 'You are not signing in'})
    if request.method != 'POST':
        return JsonResponse({'error': 'Just POST requests are supported'})
    if 'job id' not in request.POST:
        return JsonResponse({'error': 'Job identifier is not specified'})
    if 'job format' not in request.POST:
        return JsonResponse({'error': 'Job format is not specified'})
    if 'report' not in request.POST:
        return JsonResponse({'error': 'Start report is not specified'})
    if 'hash sum' not in request.POST:
        return JsonResponse({'error': 'Hash sum is not specified'})

    try:
        job = Job.objects.get(identifier__startswith=request.POST['job id'],
                              format=int(request.POST['job format']))
        request.session['job_id'] = job.id
    except ObjectDoesNotExist:
        return JsonResponse({
            'error': 'Job with the specified identifier "{0}" was not found'
            .format(request.POST['job id'])})
    except MultipleObjectsReturned:
        return JsonResponse({
            'error': 'Specified identifier "{0}" is not unique'
            .format(request.POST['job id'])})

    if not JobAccess(request.user, job).service_access():
        return JsonResponse({
            'error': 'User "{0}" has not access to job "{1}"'.format(
                request.user, job.identifier
            )
        })
    jobtar = PSIDownloadJob(job, request.POST['hash sum'])
    if jobtar.error is not None:
        return JsonResponse({
            'error': 'Couldn not prepare archive for job "{0}"'.format(
                job.identifier
            )
        })

    jobtar.memory.seek(0)
    err = UploadReport(job, json.loads(request.POST.get('report', '{}'))).error
    if err is not None:
        return JsonResponse({'error': err})

    response = HttpResponse(content_type="application/x-tar-gz")
    response["Content-Disposition"] = 'attachment; filename={0}'.format(
        jobtar.tarname)
    response.write(jobtar.memory.read())

    return response


@login_required
def getfilecontent(request):
    if request.method != 'POST':
        return JsonResponse({'message': _("Unknown error")})
    try:
        file_id = int(request.POST.get('file_id', 0))
    except ValueError:
        return JsonResponse({'message': _("Unknown error")})
    try:
        source = FileSystem.objects.get(pk=int(file_id))
    except ObjectDoesNotExist:
        return JsonResponse({'message': _("The file was not found")})
    return HttpResponse(source.file.file.read())


@login_required
def stop_decision(request):
    if request.method != 'POST':
        return JsonResponse({'error': _("Unknown error")})
    if request.user.extended.role != USER_ROLES[2][0]:
        return JsonResponse({
            'error': _("You don't have an access to stop decision of this job")
        })
    try:
        job = Job.objects.get(pk=int(request.POST.get('job_id', 0)))
    except ObjectDoesNotExist:
        return JsonResponse({'error': _("The job was not found")})
    if job.status != JOB_STATUS[1][0]:
        return JsonResponse({'error': _("The job is not solving")})
    job.status = JOB_STATUS[6][0]
    job.save()
    for report in ReportComponent.objects.filter(root__job=job):
        if report.finish_date is None:
            report.finish_date = pytz.timezone('UTC').localize(datetime.now())
            report.save()
    return JsonResponse({'status': True})


@login_required
def run_decision(request):
    if request.method != 'POST':
        return JsonResponse({'status': False, 'error': _('Unknown error')})
    try:
        job = Job.objects.get(pk=int(request.POST.get('job_id', 0)))
    except ObjectDoesNotExist:
        return JsonResponse({
            'status': False, 'error': _('The job was not found')
        })
    schedulers_ids = json.loads(request.POST.get('schedulers', '[]'))
    if not JobAccess(request.user, job):
        return JsonResponse({
            'status': False,
            'error': _("You don't have access to start decision")
        })
    try:
        job.reportroot.delete()
    except ObjectDoesNotExist:
        pass
    reportroot = ReportRoot.objects.create(user=request.user, job=job)
    for sch_id in schedulers_ids:
        try:
            scheduler = Scheduler.objects.get(pk=int(sch_id))
        except ObjectDoesNotExist:
            continue
        if scheduler.status == SCHEDULER_STATUS[0][0]:
            if scheduler.need_auth:
                scheduler_users = \
                    scheduler.scheduleruser_set.filter(user=request.user)
                if len(scheduler_users) > 0:
                    reportroot.schedulers.add(scheduler)
            else:
                reportroot.schedulers.add(scheduler)
    reportroot.save()
    if len(reportroot.schedulers.all()) == 0:
        reportroot.delete()
        return JsonResponse({
            'status': False, 'error': _('There are no available schedulers')
        })
    job.status = JOB_STATUS[1][0]
    job.save()
    return JsonResponse({'status': True})
