import collections
import copy
from typing import Dict, Union


class FlatGraphKeyGenerator:
    """
    Helper class to generate unique keys (autoincrement style)
    for processes in a flattened process graph.
    """

    def __init__(self):
        self._counters = collections.defaultdict(int)

    def generate(self, process_id: str):
        """Generate new key for given process id."""
        self._counters[process_id] += 1
        return "{p}{c}".format(p=process_id.replace('_', ''), c=self._counters[process_id])


class GraphBuilder:
    """
    Graph builder for process graphs compatible with openEO API version 1.0.0
    """

    def __init__(self, graph = None):
        """
            Create a process graph builder.
            If a graph is provided, its nodes will be added to this builder, this does not necessarily preserve id's of the nodes.

            :param graph: Dict : Optional, existing process graph
        """
        if graph is not None:
            self.result_node = graph.result_node
            self._merge_processes(graph)
        # TODO: what is result_node in "else" case?

    def shallow_copy(self):
        """
        Copy, but don't update keys
        :return:
        """
        the_copy = GraphBuilder()
        the_copy.result_node = copy.deepcopy(self.result_node)
        return the_copy

    @classmethod
    def from_process_graph(cls,graph:Dict):
        builder = GraphBuilder()
        builder.result_node = copy.deepcopy(graph)
        return builder


    def add_process(self,process_id,result=None, **args):
        process_id = self.process(process_id, args)
        if result is not None:
            self.result_node["result"] = result
        return process_id

    def process(self,process_id, args):
        """
        Add a process and return the id. Do not add a  new process if it already exists in the graph.

        :param process_id:
        :param args:
        :return:
        """
        new_process = {
            'process_id': process_id,
            'arguments': args
        }
        if 'from_node' in args:
            args['from_node'] = self.result_node
        self.result_node = new_process
        return id

    def _merge_processes(self, processes: Dict, return_key_map=False):
        # Maps original node key to new key in merged result
        key_map = {}
        node_refs = []
        for key,process in sorted(processes.items()):
            process_id = process['process_id']
            args = process['arguments']
            args_copy = copy.deepcopy(args)
            id = self.process(process_id, args_copy)
            if id != key:
                key_map[key] = id
            node_refs += self._extract_node_references(args_copy)

        for node_ref in node_refs:
            old_node_id = node_ref['from_node']
            if old_node_id in key_map:
                node_ref['from_node'] = key_map[old_node_id]

        if return_key_map:
            return self, key_map
        else:
            return self

    def _extract_node_references(self, arguments):
        node_ref_list = []
        for argument in arguments.values():
            if isinstance(argument, dict):
                if 'from_node' in argument:
                    node_ref_list.append(argument)
            if isinstance(argument,list):
                for element in argument:
                    if isinstance(element, dict):
                        if 'from_node' in element:
                            node_ref_list.append(element)
        return node_ref_list

    @classmethod
    def combine(cls, operator: str, first: Union['GraphBuilder', dict], second: Union['GraphBuilder', dict], arg_name='data'):
        """Combine two GraphBuilders to a new merged one using the given operator"""
        merged = cls()

        args = {
            arg_name:[{'from_node':first.result_node}, {'from_node':second.result_node}]
        }

        merged.add_process(operator, result=True, **args)
        return merged

    def flatten(self, key_generator: FlatGraphKeyGenerator=None):

        parent_builder = self

        if key_generator is None:
            key_generator = FlatGraphKeyGenerator()
        flat_graph = {}
        from openeo.internal.process_graph_visitor import ProcessGraphVisitor
        class Flattener(ProcessGraphVisitor):

            last_node_id = None

            def leaveProcess(self, process_id, arguments: Dict):
                node_id = key_generator.generate(process_id)
                #arguments['node_id'] = node_id
                Flattener.last_node_id = node_id
                flat_graph[node_id] = {
                    'process_id':process_id,
                    'arguments':arguments
                }

            def arrayElementDone(self,node):
                if 'from_node' in node:
                    node['from_node'] = Flattener.last_node_id

            def leaveArgument(self, argument_id, node: Dict):
                if 'from_node' in node:
                    node['from_node'] = Flattener.last_node_id
                if type(node) == dict and 'callback' in node:
                    callback = node['callback']
                    flat_callback = GraphBuilder.from_process_graph(callback).flatten(key_generator=key_generator)
                    node['callback'] = flat_callback

        flattener = Flattener()
        #take a copy, flattener modifies the graph in-place
        flattener.accept(copy.deepcopy(self.result_node))
        flat_graph[flattener.last_node_id]['result'] = True
        return flat_graph