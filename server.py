""" Simple OCPP 1.6 Server """
import asyncio
import logging
from dataclasses import asdict
from datetime import datetime

import websockets

from ocpp.charge_point import remove_nones, snake_to_camel_case
from ocpp.messages import Call, validate_payload
from ocpp.routing import on
from ocpp.v16 import ChargePoint as cp
from ocpp.v16 import call_result
from ocpp.v16.call import (ClearChargingProfilePayload,
                           SetChargingProfilePayload)
from ocpp.v16.enums import Action, RegistrationStatus
from solar_api import read_power

logging.basicConfig(level=logging.INFO)


class ChargePoint(cp):
    """ Charge Point implementation """

    _last_profile_sent = -1
    _last_max_charge = 0

    async def start(self):
        """Start the charge point."""
        while True:
            # Send smart charging profile every 1 minute
            if self._last_profile_sent != datetime.now().minute:
                max_charge, unit_power = read_power()
                if max_charge < 240:
                    max_charge = 240
                if max_charge != self._last_max_charge:
                    await self.clear_smart_charge_profile()
                    await self.set_smart_charge_profile(max_charge, unit_power)
                    self._last_max_charge = max_charge
                self._last_profile_sent = datetime.now().minute
            message = await self._connection.recv()
            logging.info('%s: receive message %s', self.id, message)  
            await self.route_message(message)

    @on(Action.BootNotification)
    def on_boot_notification(self, _charge_point_vendor: str, _charge_point_model: str, **_kwargs):
        """On boot notification."""
        return call_result.BootNotificationPayload(
            current_time=datetime.utcnow().isoformat(),
            interval=10,
            status=RegistrationStatus.accepted
        )

    @on(Action.Heartbeat)
    def on_heartbeat(self):
        """On heartbeat."""
        return call_result.HeartbeatPayload(current_time=datetime.utcnow().isoformat())

    @on(Action.MeterValues)
    def on_meter_values(self, _connector_id: int, _meter_value: list, **_kwargs):
        """On meter values."""
        return call_result.MeterValuesPayload()

    @on(Action.StatusNotification)
    def on_status_notification(self, _connector_id: int, _status: str, **_kwargs):
        """On status notification."""
        return call_result.StatusNotificationPayload()

    @on(Action.Authorize)
    def on_authorize(self, _id_tag: str, **_kwargs):
        """On authorize."""
        return call_result.AuthorizePayload(id_tag_info={'status': 'Accepted'})

    @on(Action.StartTransaction)
    def on_start_transaction(self, _connector_id: int, _id_tag: str, _meter_start: int,
                            _timestamp: datetime, **_kwargs):
        """On start transaction."""
        return call_result.StartTransactionPayload(id_tag_info={'status': 'Accepted'},
                                                    transaction_id=1)

    async def clear_smart_charge_profile(self):
        """Clear smart charging profle from charge point."""
        logging.info("Clearing smart charging profile")
        payload = ClearChargingProfilePayload()
        await self.send_payload(payload)

    async def set_smart_charge_profile(self, max_charge, charge_unit):
        """Send smart charging profle to charge point."""
        logging.info("Setting smart charging profile to %s %s", max_charge, charge_unit) 
        cs_charging_profiles = {
                'chargingProfileId': 2,
                'stackLevel': 2,
                'chargingProfilePurpose': 'ChargePointMaxProfile',
                'chargingProfileKind': 'Absolute',
                'chargingSchedule': {
                    'startSchedule': datetime.utcnow().isoformat() + 'Z',
                    'chargingRateUnit': charge_unit,
                    'chargingSchedulePeriod': [
                        {'startPeriod': 0, 'limit': max_charge}
                    ],
                   'minChargingRate': 0.1
                }
            }
        payload = SetChargingProfilePayload(
            connector_id=0,
            cs_charging_profiles=cs_charging_profiles
        )
        await self.send_payload(payload)

    async def send_payload(self, payload):
        """Send payload to charge point."""
        camel_case_payload = snake_to_camel_case(asdict(payload))
        call = Call(
            unique_id=str(self._unique_id_generator()),
            action=payload.__class__.__name__[:-7],
            payload=remove_nones(camel_case_payload)
        )
        validate_payload(call, self._ocpp_version)
        await self._send(call.to_json())

async def on_connect(websocket, path):
    """ For every new charge point that connects, create a ChargePoint
    instance and start listening for messages.
    """
    try:
        requested_protocols = websocket.request_headers[
            'Sec-WebSocket-Protocol']
    except KeyError:
        logging.error(
            "Client hasn't requested any Subprotocol. Closing Connection"
        )
        return await websocket.close()
    if websocket.subprotocol:
        logging.info("Protocols Matched: %s", websocket.subprotocol) 
    else:
        # In the websockets lib if no subprotocols are supported by the
        # client and the server, it proceeds without a subprotocol,
        # so we have to manually close the connection.
        logging.warning('Protocols Mismatched | Expected Subprotocols: %s,'
                        ' but client supports  %s | Closing connection',
                        websocket.available_subprotocols,
                        requested_protocols) 
        return await websocket.close()

    charge_point_id = path.strip('/')

    _cp = ChargePoint(charge_point_id, websocket)
    logging.info("Charge Point %s connected", _cp.id) 

    await _cp.start()


async def main():
    """Start the server."""
    server = await websockets.serve(  # type: ignore
        on_connect,
        '0.0.0.0',
        9100,
        subprotocols=['ocpp1.6']
    )

    logging.info("Server Started listening to new connections...")

    await server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
