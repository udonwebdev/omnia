"""
dlp/movement_monitor.py
Unified Data Movement Telemetry & Monitoring for OMNIA Module 52:
Autonomous Data Loss Prevention, Sensitive Information Monitoring & Exfiltration Defense Intelligence.
"""

import uuid
import time
from typing import List, Dict, Any, Optional, Tuple

from dlp.models import (
    MovementEvent, DLPChannel, EndpointEnrollment, EndpointTelemetry,
    NetworkTelemetry, CloudEvent, CommunicationEvent, RemovableMediaEvent,
    EndpointStatus, TelemetryOpType
)
from dlp.persistence import DLPRepository


class DataMovementMonitor:
    """
    Ingests and normalizes movement events across multiple telemetry channels:
    Endpoint, Network, Cloud/SaaS, Communication, Removable Media, and Clipboard.
    """

    def __init__(self, repo: DLPRepository):
        self.repo = repo

    def enroll_endpoint(
        self,
        hostname: str,
        os_type: str,
        agent_version: str = "1.0.0",
        endpoint_id: Optional[str] = None
    ) -> EndpointEnrollment:
        """Enrolls a managed host endpoint for local telemetry and transfer interception."""
        eid = endpoint_id or f"ep_{uuid.uuid4().hex[:10]}"
        now = time.time()
        ep = EndpointEnrollment(
            endpoint_id=eid,
            hostname=hostname,
            os_type=os_type,
            agent_version=agent_version,
            status=EndpointStatus.ENROLLED.value,
            enrolled_at=now,
            last_heartbeat=now,
        )
        return self.repo.save_endpoint(ep)

    def record_movement(
        self,
        actor_id: str,
        device_id: str,
        source_location: str,
        destination_location: str,
        channel: str,
        volume_bytes: int,
        is_authorized: bool = True,
        metadata: Optional[Dict[str, Any]] = None,
        event_id: Optional[str] = None
    ) -> MovementEvent:
        """Records a normalized data movement event across any DLP channel."""
        eid = event_id or f"mov_{uuid.uuid4().hex[:12]}"
        event = MovementEvent(
            event_id=eid,
            actor_id=actor_id,
            device_id=device_id,
            source_location=source_location,
            destination_location=destination_location,
            channel=channel,
            volume_bytes=volume_bytes,
            timestamp=time.time(),
            is_authorized=is_authorized,
            metadata=metadata or {},
        )
        return self.repo.save_movement_event(event)

    def record_endpoint_operation(
        self,
        endpoint_id: str,
        actor_id: str,
        operation_type: str,
        file_path: Optional[str],
        process_name: Optional[str],
        volume_bytes: int,
        destination: str = "LOCAL",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[MovementEvent, EndpointTelemetry]:
        """Ingests endpoint operation telemetry (file copy, print, clipboard, local export)."""
        now = time.time()
        channel = DLPChannel.CLIPBOARD.value if operation_type == TelemetryOpType.CLIPBOARD.value else DLPChannel.ENDPOINT.value
        
        meta = metadata.copy() if metadata else {}
        meta["operation_type"] = operation_type
        meta["process_name"] = process_name
        meta["file_path"] = file_path

        mov = self.record_movement(
            actor_id=actor_id,
            device_id=endpoint_id,
            source_location=file_path or "SYSTEM_MEMORY",
            destination_location=destination,
            channel=channel,
            volume_bytes=volume_bytes,
            is_authorized=True,
            metadata=meta
        )

        tel = EndpointTelemetry(
            telemetry_id=f"eptel_{uuid.uuid4().hex[:12]}",
            endpoint_id=endpoint_id,
            operation_type=operation_type,
            file_path=file_path,
            process_name=process_name,
            volume_bytes=volume_bytes,
            timestamp=now
        )
        self.repo.save_endpoint_telemetry(tel)
        return mov, tel

    def record_network_transfer(
        self,
        actor_id: str,
        source_ip: str,
        dest_ip: str,
        dest_domain: Optional[str],
        protocol: str,
        bytes_out: int,
        bytes_in: int = 0,
        is_encrypted: bool = True,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[MovementEvent, NetworkTelemetry]:
        """Ingests network transmission telemetry."""
        now = time.time()
        destination = dest_domain or dest_ip
        meta = metadata.copy() if metadata else {}
        meta["protocol"] = protocol
        meta["dest_domain"] = dest_domain

        mov = self.record_movement(
            actor_id=actor_id,
            device_id=source_ip,
            source_location=source_ip,
            destination_location=destination,
            channel=DLPChannel.NETWORK.value,
            volume_bytes=bytes_out,
            is_authorized=True,
            metadata=meta
        )

        net = NetworkTelemetry(
            net_telemetry_id=f"net_{uuid.uuid4().hex[:12]}",
            source_ip=source_ip,
            dest_ip=dest_ip,
            dest_domain=dest_domain,
            protocol=protocol,
            bytes_out=bytes_out,
            bytes_in=bytes_in,
            is_encrypted=is_encrypted,
            timestamp=now
        )
        self.repo.save_network_telemetry(net)
        return mov, net

    def record_cloud_action(
        self,
        actor_id: str,
        service_name: str,
        storage_target: str,
        action_type: str,
        external_recipients: Optional[List[str]] = None,
        volume_bytes: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[MovementEvent, CloudEvent]:
        """Ingests SaaS / Cloud file sharing, uploads, and exports."""
        now = time.time()
        recipients = external_recipients or []
        is_authorized = not (action_type == "SHARE_PUBLIC" or len(recipients) > 0)
        
        meta = metadata.copy() if metadata else {}
        meta["service_name"] = service_name
        meta["action_type"] = action_type
        meta["external_recipients"] = recipients

        mov = self.record_movement(
            actor_id=actor_id,
            device_id=f"cloud:{service_name}",
            source_location=f"service:{service_name}",
            destination_location=storage_target,
            channel=DLPChannel.CLOUD.value,
            volume_bytes=volume_bytes,
            is_authorized=is_authorized,
            metadata=meta
        )

        cloud = CloudEvent(
            cloud_event_id=f"cld_{uuid.uuid4().hex[:12]}",
            service_name=service_name,
            storage_target=storage_target,
            action_type=action_type,
            external_recipients=recipients,
            volume_bytes=volume_bytes,
            timestamp=now
        )
        self.repo.save_cloud_event(cloud)
        return mov, cloud

    def record_communication(
        self,
        actor_id: str,
        app_name: str,
        sender: str,
        recipients: List[str],
        attachments: Optional[List[str]] = None,
        volume_bytes: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[MovementEvent, CommunicationEvent]:
        """Ingests Email, Slack, Teams messaging events with attachment inspection."""
        now = time.time()
        att_list = attachments or []
        
        # Determine if any recipient is outside the corporate domain
        has_external = any(
            not r.endswith("@internal.corp") and not r.endswith("@omnia.local") and "@" in r
            for r in recipients
        )

        meta = metadata.copy() if metadata else {}
        meta["app_name"] = app_name
        meta["sender"] = sender
        meta["recipients"] = recipients
        meta["attachments"] = att_list
        meta["has_external_recipient"] = has_external

        mov = self.record_movement(
            actor_id=actor_id,
            device_id=f"app:{app_name}",
            source_location=sender,
            destination_location=",".join(recipients[:3]),
            channel=DLPChannel.COMMUNICATION.value,
            volume_bytes=volume_bytes,
            is_authorized=not has_external,
            metadata=meta
        )

        comm = CommunicationEvent(
            comm_event_id=f"comm_{uuid.uuid4().hex[:12]}",
            app_name=app_name,
            sender=sender,
            recipients=recipients,
            attachments=att_list,
            has_external_recipient=has_external,
            timestamp=now
        )
        self.repo.save_communication_event(comm)
        return mov, comm

    def record_removable_media(
        self,
        endpoint_id: str,
        actor_id: str,
        device_vendor: str,
        serial_number: str,
        file_name: str,
        volume_bytes: int,
        is_approved_device: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Tuple[MovementEvent, RemovableMediaEvent]:
        """Ingests USB and removable media file transfer events."""
        now = time.time()
        meta = metadata.copy() if metadata else {}
        meta["device_vendor"] = device_vendor
        meta["serial_number"] = serial_number
        meta["file_name"] = file_name
        meta["is_approved_device"] = is_approved_device

        mov = self.record_movement(
            actor_id=actor_id,
            device_id=endpoint_id,
            source_location="LOCAL_STORAGE",
            destination_location=f"USB:{device_vendor}_{serial_number}",
            channel=DLPChannel.REMOVABLE_MEDIA.value,
            volume_bytes=volume_bytes,
            is_authorized=is_approved_device,
            metadata=meta
        )

        media = RemovableMediaEvent(
            media_event_id=f"med_{uuid.uuid4().hex[:12]}",
            endpoint_id=endpoint_id,
            device_vendor=device_vendor,
            serial_number=serial_number,
            file_name=file_name,
            volume_bytes=volume_bytes,
            is_approved_device=is_approved_device,
            timestamp=now
        )
        self.repo.save_removable_media_event(media)
        return mov, media
