"""Sensor platform for Azure OpenAI conversation events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import OpenAIConfigEntry
from .const import DOMAIN, EVENT_ASSISTANT_RESPONSE, EVENT_USER_MESSAGE


@dataclass(frozen=True, kw_only=True)
class AzureOpenAIMessageSensorDescription(SensorEntityDescription):
    """Describe an Azure OpenAI message sensor."""

    event_type: str
    icon: str


SENSOR_DESCRIPTIONS: tuple[AzureOpenAIMessageSensorDescription, ...] = (
    AzureOpenAIMessageSensorDescription(
        key="last_user_message",
        translation_key="last_user_message",
        name="Last User Message",
        event_type=EVENT_USER_MESSAGE,
        icon="mdi:account-voice",
    ),
    AzureOpenAIMessageSensorDescription(
        key="last_assistant_response",
        translation_key="last_assistant_response",
        name="Last Assistant Response",
        event_type=EVENT_ASSISTANT_RESPONSE,
        icon="mdi:robot-excited",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OpenAIConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Azure OpenAI message sensors."""
    async_add_entities(
        AzureOpenAIMessageSensor(entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


class AzureOpenAIMessageSensor(RestoreEntity, SensorEntity):
    """Represent the latest Azure OpenAI conversation message."""

    entity_description: AzureOpenAIMessageSensorDescription
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        description: AzureOpenAIMessageSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        self.entity_description = description
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
        )
        self._attr_icon = description.icon
        self._message: str | None = None
        self._last_updated_iso: str | None = None
        self._extra_attributes: dict[str, Any] = {}

    @property
    def native_value(self) -> str | None:
        """Return a concise state value for the sensor."""
        return self._message[:255] if self._message else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return self._extra_attributes

    async def async_added_to_hass(self) -> None:
        """Restore state and subscribe to events when added."""
        await super().async_added_to_hass()

        if last_state := await self.async_get_last_state():
            self._extra_attributes = dict(last_state.attributes)
            last_message = self._extra_attributes.get("message")
            if isinstance(last_message, str) and last_message:
                self._message = last_message
            elif last_state.state not in (None, "unknown", "unavailable"):
                self._message = last_state.state
            self._last_updated_iso = self._extra_attributes.get("last_updated")

        @callback
        def handle_event(event: Event) -> None:
            """Handle an Azure OpenAI conversation event."""
            data = dict(event.data)
            text = data.get("text")
            self._message = text if isinstance(text, str) and text else None
            self._last_updated_iso = datetime.now(UTC).isoformat()
            self._extra_attributes = {
                "message": text,
                "last_updated": self._last_updated_iso,
                **{key: value for key, value in data.items() if key != "text"},
            }
            self.async_write_ha_state()

        self.async_on_remove(
            self.hass.bus.async_listen(self.entity_description.event_type, handle_event)
        )
