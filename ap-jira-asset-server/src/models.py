from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import relationship
from datetime import datetime

from .database import Base


class DeviceModel(Base):
    __tablename__ = "device_models"

    id = Column(String(255), primary_key=True)
    name = Column(String(500), index=True, nullable=True)
    manufacturer = Column(String(255), nullable=True)
    device_class = Column(String(255), index=True, nullable=True)   # attr 329 "class" (Wifi.Indoor, etc.)
    classtype = Column(String(255), nullable=True)                  # attr 588 lowercase variant
    zabbix_model_monitoring_mode = Column(String(255), nullable=True)
    zabbix_model_snmp_template_id = Column(String(100), nullable=True)
    meta = Column(JSON, default=dict)                               # all remaining model attributes
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    devices = relationship("Device", back_populates="model")


class Device(Base):
    __tablename__ = "devices"

    id = Column(String(255), primary_key=True)
    # Queryable indexed columns
    name = Column(String(500), index=True, nullable=True)        # label / FullName
    device_name = Column(String(500), index=True, nullable=True) # DeviceName (short, attr 383)
    ip_address = Column(String(50), index=True, nullable=True)   # management_ip
    mac_address = Column(String(50), index=True, nullable=True)  # management_mac
    serial_number = Column(String(255), index=True, nullable=True)
    object_key = Column(String(100), index=True, nullable=True)  # IHS-xxxxx
    zabbix_host_id = Column(String(100), index=True, nullable=True)
    model_id = Column(String(255), ForeignKey("device_models.id", ondelete="SET NULL"), nullable=True, index=True)
    meta = Column(JSON, default=dict)                            # all remaining attributes
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    model = relationship("DeviceModel", back_populates="devices")
    upstream_edges = relationship(
        "DeviceEdge", foreign_keys="[DeviceEdge.target_id]",
        back_populates="target", cascade="all, delete-orphan",
    )
    downstream_edges = relationship(
        "DeviceEdge", foreign_keys="[DeviceEdge.source_id]",
        back_populates="source", cascade="all, delete-orphan",
    )


class Venue(Base):
    __tablename__ = "venues"

    id = Column(String(255), primary_key=True)
    key = Column(String(100), index=True, nullable=True)            # IHS-xxxxx
    name = Column(String(500), index=True, nullable=True)
    support_engineer_id = Column(String(255), index=True, nullable=True)     # AccessParks Personel object id
    support_engineer_key = Column(String(100), nullable=True)               # IHS-xxxxx
    support_engineer_name = Column(String(255), index=True, nullable=True)
    abbreviation = Column(String(100), index=True, nullable=True)           # linked Abbreviation object's label, lowercased
    abbreviation_key = Column(String(100), nullable=True)                   # linked Abbreviation object's IHS-xxxxx key
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VenueAbbreviation(Base):
    """Abbreviation -> Venue name, for device-name-prefix zone lookups (last resort,
    used when a device can't be matched to Inventory directly by MAC/serial/name).

    One row per distinct Abbreviation object actually linked from somewhere in Jira -
    from a Venue (attr 242) or, far more commonly, from one of its Subvenues (attr 244).
    A Venue with several Subvenues, each carrying a different Abbreviation, produces
    several rows here, all pointing at that one venue_name. See
    jira_sync.build_venue_abbreviation_records for how these are built.
    """
    __tablename__ = "venue_abbreviations"

    id = Column(String(255), primary_key=True)                      # linked Abbreviation object's IHS-xxxxx key
    abbreviation = Column(String(100), index=True, nullable=False)  # lowercased label
    abbreviation_key = Column(String(100), nullable=True)           # same as id, kept for symmetry with Venue.abbreviation_key
    venue_id = Column(String(255), nullable=True)
    venue_name = Column(String(500), nullable=False)
    venue_key = Column(String(100), nullable=True)                  # IHS-xxxxx
    source = Column(String(20), nullable=False)                     # "venue" | "subvenue"
    subvenue_id = Column(String(255), nullable=True)
    subvenue_name = Column(String(500), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DeviceEdge(Base):
    """source → target means source is upstream of target."""
    __tablename__ = "device_edges"

    id = Column(String(255), primary_key=True)
    source_id = Column(String(255), ForeignKey("devices.id"), nullable=False, index=True)
    target_id = Column(String(255), ForeignKey("devices.id"), nullable=False, index=True)
    relationship_type = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    source = relationship("Device", foreign_keys=[source_id], back_populates="downstream_edges")
    target = relationship("Device", foreign_keys=[target_id], back_populates="upstream_edges")

    __table_args__ = (
        UniqueConstraint("source_id", "target_id", "relationship_type", name="uq_edge"),
    )
