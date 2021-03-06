# -*- coding: utf-8 -*-

from . import errors
from datetime import datetime

import certifi
import json
import requests


class Request(object):

    timeout = 10

    @classmethod
    def send_request_to_path(cls, method, url, auth, params=None):
        """ Construct an API request, send it to the API, and parse the
        response. """
        from intercom import __version__
        req_params = {}

        headers = {
            'User-Agent': 'python-intercom/' + __version__,
            'Accept': 'application/json'
        }
        if method in ('POST', 'PUT', 'DELETE'):
            headers['content-type'] = 'application/json'
            req_params['data'] = json.dumps(params, cls=ResourceEncoder)
        elif method == 'GET':
            req_params['params'] = params
        req_params['headers'] = headers
        resp = requests.request(
            method, url, timeout=cls.timeout,
            auth=auth, verify=certifi.where(), **req_params)

        cls.raise_errors_on_failure(resp)
        cls.set_rate_limit_details(resp)

        if resp.content:
            return cls.parse_body(resp)

    @classmethod
    def parse_body(cls, resp):
        try:
            # use supplied encoding to decode the response content
            decoded_body = resp.content.decode(resp.encoding)
            if not decoded_body:  # return early for empty responses (issue-72)
                return
            body = json.loads(decoded_body)
            if body.get('type') == 'error.list':
                cls.raise_application_errors_on_failure(body, resp.status_code)
            return body
        except ValueError:
            cls.raise_errors_on_failure(resp)

    @classmethod
    def set_rate_limit_details(cls, resp):
        rate_limit_details = {}
        headers = resp.headers
        limit = headers.get('x-ratelimit-limit', None)
        remaining = headers.get('x-ratelimit-remaining', None)
        reset = headers.get('x-ratelimit-reset', None)
        if limit:
            rate_limit_details['limit'] = int(limit)
        if remaining:
            rate_limit_details['remaining'] = int(remaining)
        if reset:
            rate_limit_details['reset_at'] = datetime.fromtimestamp(int(reset))
        from intercom import Intercom
        Intercom.rate_limit_details = rate_limit_details

    @classmethod
    def raise_errors_on_failure(cls, resp):
        if resp.status_code == 404:
            raise errors.ResourceNotFound('Resource Not Found')
        elif resp.status_code == 401:
            raise errors.AuthenticationError('Unauthorized')
        elif resp.status_code == 403:
            raise errors.AuthenticationError('Forbidden')
        elif resp.status_code == 500:
            raise errors.ServerError('Server Error')
        elif resp.status_code == 502:
            raise errors.BadGatewayError('Bad Gateway Error')
        elif resp.status_code == 503:
            raise errors.ServiceUnavailableError('Service Unavailable')

    @classmethod
    def raise_application_errors_on_failure(cls, error_list_details, http_code):  # noqa
        # Currently, we don't support multiple errors
        error_details = error_list_details['errors'][0]
        error_code = error_details.get('type')
        if error_code is None:
            error_code = error_details.get('code')
        error_context = {
            'http_code': http_code,
            'application_error_code': error_code
        }
        error_class = errors.error_codes.get(error_code)
        if error_class is None:
            # unexpected error
            if error_code:
                message = cls.message_for_unexpected_error_with_type(
                    error_details, http_code)
            else:
                message = cls.message_for_unexpected_error_without_type(
                    error_details, http_code)
            error_class = errors.UnexpectedError
        else:
            message = error_details['message']
        raise error_class(message, error_context)

    @classmethod
    def message_for_unexpected_error_with_type(cls, error_details, http_code):  # noqa
        error_type = error_details['type']
        message = error_details['message']
        return "The error of type '%s' is not recognized. It occurred with the message: %s and http_code: '%s'. Please contact Intercom with these details." % (error_type, message, http_code)  # noqa

    @classmethod
    def message_for_unexpected_error_without_type(cls, error_details, http_code):  # noqa
        message = error_details['message']
        return "An unexpected error occured. It occurred with the message: %s and http_code: '%s'. Please contact Intercom with these details." % (message, http_code)  # noqa


class ResourceEncoder(json.JSONEncoder):
    def default(self, o):
        if hasattr(o, 'attributes'):
            # handle API resources
            return o.attributes
        return super(ResourceEncoder, self).default(o)
