import socketio
from aiohttp import web
import aiohttp_cors
import json
import asyncio
from time import sleep

import input_jack as input_jack

import numpy as np
mgr = socketio.AsyncRedisManager('redis://')
sio = socketio.AsyncServer(
            client_manager=mgr,
            ping_timeout=7,
            ping_interval=3,
            cors_credentials='tidmarsh.media.mit.edu')
app = web.Application()

cors = aiohttp_cors.setup(app, defaults={
        "tidmarsh.media.mit.edu": aiohttp_cors.ResourceOptions(),
    })
sio.attach(app)

def create_socket(namespace):
    socket = TidzamSocketIO(namespace)
    sio.register_namespace(socket)
    return socket

class TidzamSocketIO(socketio.AsyncNamespace):

    def __init__(self,namespace):
        socketio.AsyncNamespace.__init__(self,namespace)

        self.external_sio   = None
        self.label_dic      = None
        self.sources        = []

    def start(self, port=80):
        web.run_app(app, port=port)

    def on_connect(self, sid, environ):
        print("** Socket IO ** connect ", sid)

    def on_disconnect(self, sid):
        print("** Socket IO ** disconnect ", sid)
        #self.livestreams.del_stream(sid)

    def create_socketClient(self):
        self.external_sio = socketio.AsyncRedisManager('redis://', write_only=True)

    def build_label_dic(self):
        classes = []
        for cl in  self.label_dic:
            classes.append('classifier-' +  cl + '.nn')
        obj =  {'sys':{'classifier':{'list':classes}}}
        return obj

    # This function is called from another Thread
    def execute(self, results, label_dic):
        if self.external_sio is None:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            print('** Socket IO **Create Redis client socket ')
            self.create_socketClient()
            print("======= TidZam RUNNING =======")

        if self.label_dic is None:
            self.label_dic = label_dic
            self.loop.run_until_complete(self.external_sio.emit('sys', self.build_label_dic() ) )
            sleep(0.1)

        resp_common = []        # Streams from public access
        resp_livestream = []    # Streams from livestreams
        for channel in results:
            outputs = {}
            for cl in range(0, len(label_dic)):
                outputs[label_dic[cl]] = float(channel["outputs"][cl])

            obj = {
                     "chan":channel["mapping"][0],
                     "analysis":{
                         "time":channel["time"],
                         "result":channel["detections"],
                         "predicitions":outputs
                     }
                 }
            if "tidzam-livestreams" in channel["mapping"][0]:
                resp_livestream.append(obj)
            else:
                resp_common.append(obj)

        self.loop.run_until_complete(self.external_sio.emit('sys', resp_common) )

        for resp in resp_livestream:
            self.loop.run_until_complete(self.external_sio.emit(resp["chan"].replace(":","-"), resp) )
        sleep(0.1)

    async def on_sys(self, sid, data):
        try:
            obj = json.loads(data)
        except:
            obj = data

        if obj["sys"].get("classifier"):
            await sio.emit('sys',self.build_label_dic())

        if obj["sys"].get("sources"):
            input_jack.SOURCES = obj["sys"]["sources"]

    def on_data(self, sid, data):
        print("** Socket IO ** data event : " + data)


cors.add(app.router.add_static('/static', 'static'), {
        "*":aiohttp_cors.ResourceOptions(allow_credentials=True)
    })
def index(request):
     with open('static/index.html') as f:
         return web.Response(text=f.read(), content_type='text/html')
app.router.add_get('/', index)
