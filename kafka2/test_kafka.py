from unittest import TestCase
from unittest.mock import Mock, patch
from getmessages_kafka2 import proc_metric_data_list
import pandas as pd
from pprint import pprint
from copy import deepcopy
import numpy as np

class TestProcMetricDataList(TestCase):
    @staticmethod
    def decode(data):
        """ self.decode a list into a dict so that the order doesn't matter """
        result = {}
        for d in deepcopy(data):
            t = d.pop('timestamp')
            for k, v in d.items():
                result.update({(k, t): v})
        return result

    def setUp(self):
        pass

    def test_one_code(self):
        # data only has one http status code, need fill 0 for 3xx, 4xx,5xx
        data = [[1, 'test.project', 'test.instance', '2xx', 1, 2, 3]]
        result = proc_metric_data_list(data)
        self.assertTrue('test.project' in result.keys())
        self.assertDictEqual(self.decode(result['test.project']),
            self.decode(
            [{'req_count_2xx[test.instance]': '3',
            'svc_mean_2xx[test.instance]': '1',
            'timestamp': '1',
            'tx_mean_2xx[test.instance]': '2'},
            {'req_count_3xx[test.instance]': '0',
            'svc_mean_3xx[test.instance]': '0',
            'timestamp': '1',
            'tx_mean_3xx[test.instance]': '0'},
            {'req_count_4xx[test.instance]': '0',
            'svc_mean_4xx[test.instance]': '0',
            'timestamp': '1',
            'tx_mean_4xx[test.instance]': '0'},
            {'req_count_5xx[test.instance]': '0',
            'svc_mean_5xx[test.instance]': '0',
            'timestamp': '1',
            'tx_mean_5xx[test.instance]': '0'}]))

    def test_one_code_with_none(self):
        # test data has null
        data = [[1, 'test.project', 'test.instance', '2xx', 1, np.nan, 3]]
        result = proc_metric_data_list(data)
        self.assertTrue('test.project' in result.keys())
        # pprint(result)
        self.assertDictEqual(self.decode(result['test.project']),
            self.decode(
                         [{'req_count_2xx[test.instance]': '3.0',
                            'svc_mean_2xx[test.instance]': '1.0',
                            'timestamp': '1',
                            'tx_mean_2xx[test.instance]': '0.0'},
                            {'req_count_5xx[test.instance]': '0',
                            'svc_mean_5xx[test.instance]': '0',
                            'timestamp': '1',
                            'tx_mean_5xx[test.instance]': '0'},
                            {'req_count_4xx[test.instance]': '0',
                            'svc_mean_4xx[test.instance]': '0',
                            'timestamp': '1',
                            'tx_mean_4xx[test.instance]': '0'},
                            {'req_count_3xx[test.instance]': '0',
                            'svc_mean_3xx[test.instance]': '0',
                            'timestamp': '1',
                            'tx_mean_3xx[test.instance]': '0'}]))

    def test_three_instances(self):
        # 3 instances with 3 codes, should fill 0 for 5xx
        data = [[i, 'test.project', 'test.instance',
            f'{i}xx', 1, 2, 3] for i in [2, 3, 4]]

        result = proc_metric_data_list(data)
        self.assertTrue('test.project' in result.keys())
        self.assertDictEqual(self.decode(result['test.project']), self.decode(
              [{'req_count_2xx[test.instance]': '3',
                'svc_mean_2xx[test.instance]': '1',
                'timestamp': '2',
                'tx_mean_2xx[test.instance]': '2'},
                {'req_count_3xx[test.instance]': '3',
                'svc_mean_3xx[test.instance]': '1',
                'timestamp': '3',
                'tx_mean_3xx[test.instance]': '2'},
                {'req_count_4xx[test.instance]': '3',
                'svc_mean_4xx[test.instance]': '1',
                'timestamp': '4',
                'tx_mean_4xx[test.instance]': '2'},
                {'req_count_5xx[test.instance]': '0',
                'svc_mean_5xx[test.instance]': '0',
                'timestamp': '4',
                'tx_mean_5xx[test.instance]': '0'}]))

    def test_two_projects(self):
        # test with two projects
        data = [[i, f'test.project{i}', 'test.instance',
            f'{i}xx', 1, 2, 3] for i in [2, 3]]

        result = proc_metric_data_list(data)

        self.assertEqual(len(result.keys()), 2)
        self.assertDictEqual(self.decode(result['test.project2']),
            self.decode([{'req_count_2xx[test.instance]': '3',
                                'svc_mean_2xx[test.instance]': '1',
                                'timestamp': '2',
                                'tx_mean_2xx[test.instance]': '2'},
                               {'req_count_4xx[test.instance]': '0',
                                'svc_mean_4xx[test.instance]': '0',
                                'timestamp': '3',
                                'tx_mean_4xx[test.instance]': '0'},
                               {'req_count_5xx[test.instance]': '0',
                                'svc_mean_5xx[test.instance]': '0',
                                'timestamp': '3',
                                'tx_mean_5xx[test.instance]': '0'},
                               {'req_count_3xx[test.instance]': '0',
                                'svc_mean_3xx[test.instance]': '0',
                                'timestamp': '3',
                                'tx_mean_3xx[test.instance]': '0'}]
            ))

        self.assertDictEqual(self.decode(result['test.project3']),
            self.decode([{'req_count_3xx[test.instance]': '3',
                                'svc_mean_3xx[test.instance]': '1',
                                'timestamp': '3',
                                'tx_mean_3xx[test.instance]': '2'},
                               {'req_count_4xx[test.instance]': '0',
                                'svc_mean_4xx[test.instance]': '0',
                                'timestamp': '3',
                                'tx_mean_4xx[test.instance]': '0'},
                               {'req_count_5xx[test.instance]': '0',
                                'svc_mean_5xx[test.instance]': '0',
                                'timestamp': '3',
                                'tx_mean_5xx[test.instance]': '0'},
                               {'req_count_2xx[test.instance]': '0',
                                'svc_mean_2xx[test.instance]': '0',
                                'timestamp': '3',
                                'tx_mean_2xx[test.instance]': '0'}]
            )
        )

    def tearDown(self):
        pass
