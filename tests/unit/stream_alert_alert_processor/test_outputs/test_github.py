"""
Copyright 2017-present, Airbnb Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""
# pylint: disable=protected-access,attribute-defined-outside-init,no-self-use
import base64

from mock import patch
from moto import mock_s3, mock_kms
from nose.tools import assert_false, assert_true, assert_equal, assert_is_not_none

from stream_alert.alert_processor.outputs.github import GithubOutput
from tests.unit.stream_alert_alert_processor import (
    KMS_ALIAS,
    MOCK_ENV,
    REGION
)
from tests.unit.stream_alert_alert_processor.helpers import (
    get_alert,
    put_mock_creds,
    remove_temp_secrets
)


@patch('stream_alert.alert_processor.outputs.output_base.OutputDispatcher.MAX_RETRY_ATTEMPTS', 1)
class TestGithubOutput(object):
    """Test class for GithubOutput"""
    DESCRIPTOR = 'unit_test_repo'
    SERVICE = 'github'
    OUTPUT = ':'.join([SERVICE, DESCRIPTOR])
    CREDS = {'username': 'unit_test_user', 'access_token':
             'unit_test_access_token', 'repository': 'unit_test_org/unit_test_repo',
             'labels': 'label1,label2'}

    @patch.dict('os.environ', MOCK_ENV)
    def setup(self):
        """Setup before each method"""
        self._mock_s3 = mock_s3()
        self._mock_s3.start()
        self._mock_kms = mock_kms()
        self._mock_kms.start()
        self._dispatcher = GithubOutput(None)
        remove_temp_secrets()
        output_name = self._dispatcher.output_cred_name(self.DESCRIPTOR)
        put_mock_creds(output_name, self.CREDS, self._dispatcher.secrets_bucket, REGION, KMS_ALIAS)

    def teardown(self):
        """Teardown after each method"""
        self._mock_s3.stop()
        self._mock_kms.stop()

    @patch('logging.Logger.info')
    @patch('requests.post')
    def test_dispatch_success(self, url_mock, log_mock):
        """GithubOutput - Dispatch Success"""
        url_mock.return_value.status_code = 200
        url_mock.return_value.json.return_value = dict()

        assert_true(self._dispatcher.dispatch(get_alert(), self.OUTPUT))

        assert_equal(url_mock.call_args[0][0],
                     'https://api.github.com/repos/unit_test_org/unit_test_repo/issues')
        assert_is_not_none(url_mock.call_args[1]['headers']['Authorization'])

        credentials = url_mock.call_args[1]['headers']['Authorization'].split(' ')[-1]
        decoded_username_password = base64.b64decode(credentials)
        assert_equal(decoded_username_password, '{}:{}'.format(self.CREDS['username'],
                                                               self.CREDS['access_token']))

        log_mock.assert_called_with('Successfully sent alert to %s:%s',
                                    self.SERVICE, self.DESCRIPTOR)

    @patch('logging.Logger.info')
    @patch('requests.post')
    def test_dispatch_success_with_labels(self, url_mock, log_mock):
        """GithubOutput - Dispatch Success with Labels"""
        url_mock.return_value.status_code = 200
        url_mock.return_value.json.return_value = dict()

        assert_true(self._dispatcher.dispatch(get_alert(), self.OUTPUT))

        assert_equal(url_mock.call_args[1]['json']['labels'], ['label1', 'label2'])
        log_mock.assert_called_with('Successfully sent alert to %s:%s',
                                    self.SERVICE, self.DESCRIPTOR)

    @patch('logging.Logger.error')
    @patch('requests.post')
    def test_dispatch_failure(self, url_mock, log_mock):
        """GithubOutput - Dispatch Failure, Bad Request"""
        json_error = {'message': 'error message', 'errors': ['error1']}
        url_mock.return_value.json.return_value = json_error
        url_mock.return_value.status_code = 400

        assert_false(self._dispatcher.dispatch(get_alert(), self.OUTPUT))

        log_mock.assert_called_with('Failed to send alert to %s:%s', self.SERVICE, self.DESCRIPTOR)

    @patch('logging.Logger.error')
    def test_dispatch_bad_descriptor(self, log_mock):
        """GithubOutput - Dispatch Failure, Bad Descriptor"""
        assert_false(
            self._dispatcher.dispatch(get_alert(), ':'.join([self.SERVICE, 'bad_descriptor'])))

        log_mock.assert_called_with('Failed to send alert to %s:%s', self.SERVICE, 'bad_descriptor')
