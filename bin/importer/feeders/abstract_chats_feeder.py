#!/usr/bin/env python3
# -*-coding:UTF-8 -*
"""
Abstract Chat JSON Feeder Importer Module
================

Process Feeder Json (example: Twitter feeder)

"""
import datetime
import os
import sys

from abc import ABC

sys.path.append(os.environ['AIL_BIN'])
##################################
# Import Project packages
##################################
from importer.feeders.Default import DefaultFeeder
from lib.objects.Chats import Chat
from lib.objects import ChatSubChannels
from lib.objects import ChatThreads
from lib.objects import Images
from lib.objects import Messages
from lib.objects import FilesNames
# from lib.objects import Files
from lib.objects import UsersAccount
from lib.objects.Usernames import Username
from lib import chats_viewer

import base64
import io
import gzip

# TODO remove compression ???
def _gunzip_bytes_obj(bytes_obj):
    gunzipped_bytes_obj = None
    try:
        in_ = io.BytesIO()
        in_.write(bytes_obj)
        in_.seek(0)

        with gzip.GzipFile(fileobj=in_, mode='rb') as fo:
            gunzipped_bytes_obj = fo.read()
    except Exception as e:
        print(f'Global; Invalid Gzip file: {e}')

    return gunzipped_bytes_obj

class AbstractChatFeeder(DefaultFeeder, ABC):

    def __init__(self, name, json_data):
        super().__init__(json_data)
        self.obj = None
        self.name = name

    def get_chat_protocol(self):  # TODO # # # # # # # # # # # # #
        return self.name

    def get_chat_network(self):
        self.json_data['meta'].get('network', None)

    def get_chat_address(self):
        self.json_data['meta'].get('address', None)

    def get_chat_instance_uuid(self):
        chat_instance_uuid = chats_viewer.create_chat_service_instance(self.get_chat_protocol(),
                                                                       network=self.get_chat_network(),
                                                                       address=self.get_chat_address())
        # TODO SET
        return chat_instance_uuid

    def get_chat_id(self):  # TODO RAISE ERROR IF NONE
        return self.json_data['meta']['chat']['id']

    def get_subchannel_id(self):
        return self.json_data['meta']['chat'].get('subchannel', {}).get('id')

    def get_subchannels(self):
        pass

    def get_thread_id(self):
        return self.json_data['meta'].get('thread', {}).get('id')

    def get_message_id(self):
        return self.json_data['meta']['id']

    def get_media_name(self):
        return self.json_data['meta'].get('media', {}).get('name')

    def get_reactions(self):
        return self.json_data['meta'].get('reactions', [])

    def get_message_timestamp(self):
        if not self.json_data['meta'].get('date'):
            return None
        else:
            return self.json_data['meta']['date']['timestamp']
        # if self.json_data['meta'].get('date'):
        #     date = datetime.datetime.fromtimestamp( self.json_data['meta']['date']['timestamp'])
        #     date = date.strftime('%Y/%m/%d')
        # else:
        #     date = datetime.date.today().strftime("%Y/%m/%d")

    def get_message_date_timestamp(self):
        timestamp = self.get_message_timestamp()
        date = datetime.datetime.fromtimestamp(timestamp)
        date = date.strftime('%Y%m%d')
        return date, timestamp

    def get_message_sender_id(self):
        return self.json_data['meta']['sender']['id']

    def get_message_reply(self):
        return self.json_data['meta'].get('reply_to')  # TODO change to reply ???

    def get_message_reply_id(self):
        return self.json_data['meta'].get('reply_to', {}).get('message_id')

    def get_message_forward(self):
        return self.json_data['meta'].get('forward')

    def get_message_content(self):
        decoded = base64.standard_b64decode(self.json_data['data'])
        return _gunzip_bytes_obj(decoded)

    def get_obj(self):
        #### TIMESTAMP ####
        timestamp = self.get_message_timestamp()

        #### Create Object ID ####
        chat_id = self.get_chat_id()
        try:
            message_id = self.get_message_id()
        except KeyError:
            if chat_id:
                self.obj = Chat(chat_id, self.get_chat_instance_uuid())
                return self.obj
            else:
                self.obj = None
                return None

        thread_id = self.get_thread_id()
        # channel id
        # thread id

        # TODO sanitize obj type
        obj_type = self.get_obj_type()

        if obj_type == 'image':
            self.obj = Images.Image(self.json_data['data-sha256'])

        else:
            obj_id = Messages.create_obj_id(self.get_chat_instance_uuid(), chat_id, message_id, timestamp, thread_id=thread_id)
            self.obj = Messages.Message(obj_id)
        return self.obj

    def process_chat(self, new_objs, obj, date, timestamp, reply_id=None):
        meta = self.json_data['meta']['chat'] # todo replace me by function
        chat = Chat(self.get_chat_id(), self.get_chat_instance_uuid())
        subchannel = None
        thread = None

        # date stat + correlation
        chat.add(date, obj)

        if meta.get('name'):
            chat.set_name(meta['name'])

        if meta.get('info'):
            chat.set_info(meta['info'])

        if meta.get('date'): # TODO check if already exists
            chat.set_created_at(int(meta['date']['timestamp']))

        if meta.get('icon'):
            img = Images.create(meta['icon'], b64=True)
            img.add(date, chat)
            chat.set_icon(img.get_global_id())
            new_objs.add(img)

        if meta.get('username'):
            username = Username(meta['username'], self.get_chat_protocol())
            chat.update_username_timeline(username.get_global_id(), timestamp)

        if meta.get('subchannel'):
            subchannel, thread = self.process_subchannel(obj, date, timestamp, reply_id=reply_id)
            chat.add_children(obj_global_id=subchannel.get_global_id())
        else:
            if obj.type == 'message':
                if self.get_thread_id():
                    thread = self.process_thread(obj, chat, date, timestamp, reply_id=reply_id)
                else:
                    chat.add_message(obj.get_global_id(), self.get_message_id(), timestamp, reply_id=reply_id)

        chats_obj = [chat]
        if subchannel:
            chats_obj.append(subchannel)
        if thread:
            chats_obj.append(thread)
        return chats_obj

    def process_subchannel(self, obj, date, timestamp, reply_id=None):  # TODO CREATE DATE
        meta = self.json_data['meta']['chat']['subchannel']
        subchannel = ChatSubChannels.ChatSubChannel(f'{self.get_chat_id()}/{meta["id"]}', self.get_chat_instance_uuid())
        thread = None

        # TODO correlation with obj = message/image
        subchannel.add(date)

        if meta.get('date'): # TODO check if already exists
            subchannel.set_created_at(int(meta['date']['timestamp']))

        if meta.get('name'):
            subchannel.set_name(meta['name'])
            # subchannel.update_name(meta['name'], timestamp) # TODO #################

        if meta.get('info'):
            subchannel.set_info(meta['info'])

        if obj.type == 'message':
            if self.get_thread_id():
                thread = self.process_thread(obj, subchannel, date, timestamp, reply_id=reply_id)
            else:
                subchannel.add_message(obj.get_global_id(), self.get_message_id(), timestamp, reply_id=reply_id)
        return subchannel, thread

    def process_thread(self, obj, obj_chat, date, timestamp, reply_id=None):
        meta = self.json_data['meta']['thread']
        thread_id = self.get_thread_id()
        p_chat_id = meta['parent'].get('chat')
        p_subchannel_id = meta['parent'].get('subchannel')
        p_message_id = meta['parent'].get('message')

        # print(thread_id, p_chat_id, p_subchannel_id, p_message_id)

        if p_chat_id == self.get_chat_id() and p_subchannel_id == self.get_subchannel_id():
            thread = ChatThreads.create(thread_id, self.get_chat_instance_uuid(), p_chat_id, p_subchannel_id, p_message_id, obj_chat)
            thread.add(date, obj)
            thread.add_message(obj.get_global_id(), self.get_message_id(), timestamp, reply_id=reply_id)
            # TODO OTHERS CORRELATIONS TO ADD

            if meta.get('name'):
                thread.set_name(meta['name'])

            return thread

        # TODO
        # else:
        #   # ADD NEW MESSAGE REF (used by discord)

    def process_sender(self, new_objs, obj, date, timestamp):
        meta = self.json_data['meta'].get('sender')
        if not meta:
            return None

        user_account = UsersAccount.UserAccount(meta['id'], self.get_chat_instance_uuid())

        # date stat + correlation
        user_account.add(date, obj)

        if meta.get('username'):
            username = Username(meta['username'], self.get_chat_protocol())
            # TODO timeline or/and correlation ????
            user_account.add_correlation(username.type, username.get_subtype(r_str=True), username.id)
            user_account.update_username_timeline(username.get_global_id(), timestamp)

            # Username---Message
            username.add(date)  # TODO # correlation message ???

        # ADDITIONAL METAS
        if meta.get('firstname'):
            user_account.set_first_name(meta['firstname'])
        if meta.get('lastname'):
            user_account.set_last_name(meta['lastname'])
        if meta.get('phone'):
            user_account.set_phone(meta['phone'])

        if meta.get('icon'):
            img = Images.create(meta['icon'], b64=True)
            img.add(date, user_account)
            user_account.set_icon(img.get_global_id())
            new_objs.add(img)

        if meta.get('info'):
            user_account.set_info(meta['info'])

        return user_account

    def process_meta(self):  # TODO CHECK MANDATORY FIELDS
        """
        Process JSON meta filed.
        """
        # meta = self.get_json_meta()

        objs = set()
        if self.obj:
            objs.add(self.obj)
        new_objs = set()

        date, timestamp = self.get_message_date_timestamp()

        # REPLY
        reply_id = self.get_message_reply_id()

        print(self.obj.type)

        # TODO FILES + FILES REF

        # get object by meta object type
        if self.obj.type == 'message':
            # Content
            obj = Messages.create(self.obj.id, self.get_message_content())

            # FILENAME
            media_name = self.get_media_name()
            if media_name:
                print(media_name)
                FilesNames.FilesNames().create(media_name, date, obj)

            for reaction in self.get_reactions():
                obj.add_reaction(reaction['reaction'], int(reaction['count']))
        elif self.obj.type == 'chat':
            pass
        else:
            chat_id = self.get_chat_id()
            thread_id = self.get_thread_id()
            channel_id = self.get_subchannel_id()
            message_id = self.get_message_id()
            message_id = Messages.create_obj_id(self.get_chat_instance_uuid(), chat_id, message_id, timestamp, channel_id=channel_id, thread_id=thread_id)
            message = Messages.Message(message_id)
            # create empty message if message don't exist
            if not message.exists():
                message.create('')
                objs.add(message)

            if message.exists(): # TODO Correlation user-account image/filename ????
                obj = Images.create(self.get_message_content())
                obj.add(date, message)
                obj.set_parent(obj_global_id=message.get_global_id())

                # FILENAME
                media_name = self.get_media_name()
                if media_name:
                    FilesNames.FilesNames().create(media_name, date, message, file_obj=obj)

                for reaction in self.get_reactions():
                    message.add_reaction(reaction['reaction'], int(reaction['count']))

        for obj in objs:  # TODO PERF avoid parsing metas multiple times

            # TODO get created subchannel + thread
            #    => create correlation user-account with object

            print(obj.id)

            # CHAT
            chat_objs = self.process_chat(new_objs, obj, date, timestamp, reply_id=reply_id)

            # Message forward
            # if self.get_json_meta().get('forward'):
            #     forward_from = self.get_message_forward()
            #     print('-----------------------------------------------------------')
            #     print(forward_from)
            #     if forward_from:
            #         forward_from_type = forward_from['from']['type']
            #         if forward_from_type == 'channel' or forward_from_type == 'chat':
            #             chat_forward_id = forward_from['from']['id']
            #             chat_forward = Chat(chat_forward_id, self.get_chat_instance_uuid())
            #             if chat_forward.exists():
            #                 for chat_obj in chat_objs:
            #                     if chat_obj.type == 'chat':
            #                         chat_forward.add_relationship(chat_obj.get_global_id(), 'forward')
            #                         # chat_forward.add_relationship(obj.get_global_id(), 'forward')

            # SENDER # TODO HANDLE NULL SENDER
            user_account = self.process_sender(new_objs, obj, date, timestamp)

            if user_account:
            # UserAccount---ChatObjects
                for obj_chat in chat_objs:
                    user_account.add_correlation(obj_chat.type, obj_chat.get_subtype(r_str=True), obj_chat.id)

            # if chat: # TODO Chat---Username correlation ???
            #     # Chat---Username    => need to handle members and participants
            #     chat.add_correlation(username.type, username.get_subtype(r_str=True), username.id)

            # TODO Sender image -> correlation
                # image
                #       -> subchannel ?
                #       -> thread id ?

        return new_objs | objs
