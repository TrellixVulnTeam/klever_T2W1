import http.cookiejar
import json
import time
import urllib.error
import urllib.parse
import urllib.request


class Session:
    def __init__(self, logger, omega, job_id):
        logger.info('Create session for user "{0}" at Omega "{1}"'.format(omega['user'], omega['name']))

        self.logger = logger
        self.name = omega['name']
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.csrftoken = None

        # TODO: try to autentificate like with httplib2.Http().add_credentials().
        # Get initial value of CSRF token via useless GET request.
        self.__request('users/psi_signin/')

        # Sign in.
        self.__request('users/psi_signin/', {
            'username': omega['user'],
            'password': omega['passwd'],
            'job identifier': job_id
        })
        logger.debug('Session was created')

    def __request(self, path_url, data=None):
        url = 'http://' + self.name + '/' + path_url

        # Presence of data implies POST request.
        method = 'POST' if data else 'GET'

        self.logger.debug('Send "{0}" request to "{1}"'.format(method, url))

        if data:
            data.update({'csrfmiddlewaretoken': self.csrftoken})

        while True:
            try:
                if data:
                    resp = self.opener.open(url, urllib.parse.urlencode(data).encode('utf-8'))
                else:
                    resp = self.opener.open(url)

                # Update CSRF token after each request although it isn't likely changed. There is no good stable rules
                # describing when CSRF token does can change.
                for cookie in self.cj:
                    if cookie.name == 'csrftoken':
                        self.csrftoken = cookie.value

                if resp.headers['content-type'] == 'application/json':
                    resp_json = json.loads(resp.read().decode('utf-8'))

                    if 'error' in resp_json:
                        raise IOError(
                            'Got error "{0}" when send "{1}" request to "{2}"'.format(resp_json['error'], method, url))

                    return resp

                return resp
            except urllib.error.HTTPError as err:
                with open('response error.html', 'w') as fp:
                    fp.write(err.read().decode('utf-8'))
                raise IOError(
                    'Got unexpected status code "{0}" when send "{1}" request to "{2}"'.format(err.code, method, url))
            except urllib.error.URLError as err:
                self.logger.warning('Could not send "{0}" request to "{1}": {2}'.format(method, url, err.reason))
                time.sleep(1)

    def decide_job(self, job, start_report_file):
        # TODO: report is likely should be compressed.
        with open(start_report_file) as fp:
            resp = self.__request('jobs/decide_job/', {
                'job format': job.format,
                'report': fp.read()
            })

        self.logger.debug('Write job archive to "{0}'.format(job.archive))
        with open(job.archive, 'wb') as fp:
            while True:
                chunk = resp.read(1024)
                if not chunk:
                    break
                fp.write(chunk)

    def sign_out(self):
        self.logger.info('Finish session')
        self.__request('users/psi_signout/')

    def upload_report(self, report):
        # TODO: report is likely should be compressed.
        self.__request('reports/upload/', {'report': report})
