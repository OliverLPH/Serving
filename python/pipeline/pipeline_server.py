#   Copyright (c) 2020 PaddlePaddle Authors. All Rights Reserved.
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
# pylint: disable=doc-string-missing
from concurrent import futures
import grpc
import logging
import socket
from contextlib import closing
import yaml

from .proto import pipeline_service_pb2_grpc
from .operator import ResponseOp
from .dag import DAGExecutor

_LOGGER = logging.getLogger()


class PipelineService(pipeline_service_pb2_grpc.PipelineServiceServicer):
    def __init__(self, dag_executor):
        super(PipelineService, self).__init__()
        self._dag_executor = dag_executor
        self._dag_executor.start()

    def inference(self, request, context):
        resp = self._dag_executor.call(request)
        return resp


class PipelineServer(object):
    def __init__(self):
        self._port = None
        self._worker_num = None
        self._response_op = None

    def set_response_op(self, response_op):
        if not isinstance(response_op, ResponseOp):
            raise Exception("response_op must be ResponseOp type.")
        if len(response_op.get_input_ops()) != 1:
            raise Exception("response_op can only have one previous op.")
        self._response_op = response_op

    def _port_is_available(self, port):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(2)
            result = sock.connect_ex(('0.0.0.0', port))
        return result != 0

    def prepare_server(self, yml_file):
        with open(yml_file) as f:
            yml_config = yaml.load(f.read())
        self._port = yml_config.get('port', 8080)
        if not self._port_is_available(self._port):
            raise SystemExit("Prot {} is already used".format(self._port))
        self._worker_num = yml_config.get('worker_num', 2)

        # init dag executor
        self._dag_executor = DAGExecutor(self._response_op, yml_config)

    def run_server(self):
        service = PipelineService(self._dag_executor)
        server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=self._worker_num))
        pipeline_service_pb2_grpc.add_PipelineServiceServicer_to_server(service,
                                                                        server)
        server.add_insecure_port('[::]:{}'.format(self._port))
        server.start()
        server.wait_for_termination()
