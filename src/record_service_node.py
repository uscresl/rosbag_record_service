#!/usr/bin/python

"""
This file defines the serving node for managing ROS records
"""

PKG = "rosbag_record_service"
import datetime
import roslib; roslib.load_manifest(PKG)
import os
import subprocess
from rosbag_record_service.srv import *
from rosbag_record_service.msg import *
import rospy
import signal


class ArgStruct:
    """
    Class to maintain options passed for each request.
    Constructs appropriate command strings.
    """
    def __init__(self):
        self.regex = ''
        self.exclude_regex = ''
        self.quiet = True
        self.output_prefix = ''
        self.output_folder = ''
        self.split_size = 0
        self.topics = list()
        self.all = False
        self.error = None
        self.compression = ''

    def command_string(self, dt=None):
        """
        Generates a command string that represents appropriately the settings parsed
        """
        command_parts = ['rosbag record']
        if self.all:  # Then we record all topics
            command_parts.append('-a')
        if self.quiet:  # Then nothing is output to the console
            command_parts.append('-q')
        if self.regex != '':  # This is to include topics that match certain a certain regex
            command_parts.append('-e %s' % self.regex)
        if self.exclude_regex != '':  # This is to exclude certain topics
            command_parts.append('-x %s' % self.exclude_regex)
        if self.split_size > 0:  # Bag files are split into parts if they get too big
            command_parts.append('--split --size=%s' % self.split_size)
        if self.compression in ('bz2', 'lz4'): # Compression
            command_parts.append('--%s' % self.compression)
        output_folder = self.output_folder
        if output_folder == '':
            output_folder = '/tmp/'
        output_folder = os.path.expandvars(os.path.expanduser(output_folder))
        if dt is None:
            dt = datetime.datetime.now()
        output_folder = dt.strftime(output_folder)
        if not os.path.isdir(output_folder):
            try:
                os.makedirs(output_folder)  # Make this directory to group today's bags
            except Exception as e:
                rospy.logerr("Not able to create directory: %s" % output_folder)
                raise e
        output_prefix = os.path.expandvars(dt.strftime(self.output_prefix))
        command_parts.append('-o %s' % os.path.join(output_folder,output_prefix))
        if not self.all:
            command_parts.append(' '.join(self.topics))
        return ' '.join(command_parts)


class RecordServiceNode:
    """
    Node Service that can be called to start or stop recording certain ROS topics.
    Extends @rosbag
    """
    def __init__(self):
        self.bag_record_map = dict()  # This maintains a map of groups being recorded and their PIDs
        self.topic_groups = dict() # Maintains the arguments for each topic group loaded from config

        self.service_name = "record_service"
        rospy.init_node(self.service_name)
        self.load_config()
        self.publisher = rospy.Publisher("~status", RecordMsg, queue_size=1, latch=True)
        self.service = rospy.Service(self.service_name, RecordSrv, self.request_handler)
        self.service = rospy.Service("~multi", RecordSrvMulti, self.request_handler_multi)
        self.publish_topics()
        self.spin()

    def spin(self):
        r = rospy.Rate(1)

        while not rospy.is_shutdown():
            completed_processes = list()
            for topic_group in self.bag_record_map:
                return_code = self.bag_record_map[topic_group].poll()
                if return_code is not None:
                    something_has_changed = True
                    if return_code == 0:
                        rospy.loginfo("%s has stopped recording successfully" % topic_group)
                    else:
                        rospy.logwarn("%s has stopped recording with code: %s" % (topic_group, return_code))
                    completed_processes.append(topic_group)

            if len(completed_processes) > 0:
                for topic_group in completed_processes:
                    self.bag_record_map.pop(topic_group)  # This is not being recorded anymore
                self.publish_topics()
            r.sleep()

    def publish_topics(self):
        """
        Publish the currently active topic groups
        """
        msg = RecordMsg()
        #msg.topics = self.bag_record_map.keys()
        msg.groups = self.topic_groups.keys()
        msg.statuses = [group in self.bag_record_map for group in msg.groups]
        self.publisher.publish(msg)

    def request_handler(self, request):
        """
        Handles all incoming requests to this service
        :param request: type(RecordSrvRequest) - (action, topic_group)
        :return: RecordSrvResponse - (return_code)
        """
        return_code = self.handle_topic_group(request.topic_group, request.action)
        self.publish_topics()
        return RecordSrvResponse(return_code=return_code)

    def request_handler_multi(self, request):
        """
        Handles all incoming requests to this service
        :param request: type(RecordSrvMultiRequest) - (action, topic_groups)
        :return: RecordSrvMultiResponse - (return_codes)
        """
        dt = datetime.datetime.now()
        return_codes = []
        for topic_group in request.topic_groups:
            return_codes.append(self.handle_topic_group(topic_group, request.action, dt=dt))
        self.publish_topics()
        return RecordSrvMultiResponse(return_codes=return_codes)


    def handle_topic_group(self, topic_group, action, dt=None):
        if action == RecordSrvRequest.START:
            if topic_group in self.bag_record_map:
                # This means there is already a process running for the same group. We don't need another process
                return RecordSrvResponse.ALREADY_RECORDING

            # Check if this topic groups exists
            if topic_group not in self.topic_groups:
                # Topic group does not exist, return error
                return RecordSrvResponse.INVALID_GROUP

            # Get arg struct for this topic group
            arg_struct = self.topic_groups[topic_group]

            if arg_struct.error is not None:
                # Then there is an error; return immediately
                return RecordSrvResponse.ERROR

            # If we are here, then there was no error and we have to start another process for a group
            try:
                command = arg_struct.command_string(dt=dt)
            except IOError as e:
                rospy.logerr(str(e))
                return RecordSrvResponse.ERROR

            child_process = subprocess.Popen(command.split())
            r = rospy.sleep(0.1)  # Sleep for a while, to possibly allow the process to parse the input

            return_code = child_process.poll()
            if not (return_code is None or return_code == 0):
                rospy.logerr("Error parsing inputs")
                return RecordSrvResponse.ERROR

            self.bag_record_map[topic_group] = child_process
            rospy.loginfo("Started recording: %s" % topic_group)
            return RecordSrvResponse.OK

        elif action == RecordSrvRequest.STOP:
            if topic_group in self.bag_record_map:
                child_process = self.bag_record_map.pop(topic_group)
                self.kill_process_tree(child_process)
                rospy.loginfo("Stopped recording: %s" % topic_group)
                return RecordSrvResponse.OK
            else:
                return RecordSrvResponse.NOT_RUNNING

        else:
            return RecordSrvResponse.INVALID_ACTION

    @staticmethod
    def kill_process_tree(process):
        """
        Kills the process and all of its children
        :param process: A subprocess.Popen object
        :return:
        """
        ps_command = subprocess.Popen("ps -o pid --ppid %d --noheaders" % process.pid,
                                      shell=True, stdout=subprocess.PIPE)
        ps_output = ps_command.stdout.read()
        ps_command.wait()
        for pid_str in ps_output.split("\n")[:-1]:
            os.kill(int(pid_str), signal.SIGINT)
        process.terminate()
        process.wait()

    def load_config(self):
        """
        Loads the configuration from the ros parameter server and generates ArgStructs
        for each of them and places in the topic_groups dict.
        """
        output_folder = rospy.get_param('~output_folder','')
        split_size = rospy.get_param('~split_size',0)
        quiet = rospy.get_param('~quiet',True)
        exclude = rospy.get_param('~exclude','')
        compression = rospy.get_param('~compression','')

        for group_name, group_settings in rospy.get_param('~topic_groups', {}).items():
            arg_struct = ArgStruct()
            arg_struct.regex = group_settings.get('regex', '')
            arg_struct.all = group_settings.get('all', False)
            arg_struct.output_prefix = group_settings.get('output_prefix', '')
            arg_struct.topics = group_settings.get('topics', [])

            arg_struct.exclude_regex = group_settings.get('exclude', exclude)
            arg_struct.output_folder = group_settings.get('output_folder', output_folder)
            arg_struct.split_size = group_settings.get('split_size', split_size)
            arg_struct.quiet = group_settings.get('quiet', quiet)
            arg_struct.compression = group_settings.get('compression', compression)
            self.topic_groups[group_name] = arg_struct


if __name__ == "__main__":
    n = RecordServiceNode()
