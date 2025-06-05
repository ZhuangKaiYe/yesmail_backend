import json
from channels.generic.websocket import AsyncWebsocketConsumer


class MailConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.username = self.scope['url_route']['kwargs']['username']
        self.room_group_name = f"user_{self.username}"
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        pass

    async def new_mail(self, event):
        await self.send(text_data=json.dumps({
            'type': 'new_mail',
            'subject': event['subject'],
            'from': event['from_email'],
        }))
