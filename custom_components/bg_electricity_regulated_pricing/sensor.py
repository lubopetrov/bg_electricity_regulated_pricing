"""Sensor platform for bg_electricity_regulated_pricing integration."""
from __future__ import annotations

from datetime import datetime
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, \
    SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import utcnow

from .const import CONF_TARIFF_TYPE, CONF_PROVIDER, CONF_CUSTOM_DAY_PRICE, \
    CONF_CUSTOM_NIGHT_PRICE, CONF_CLOCK_OFFSET, \
    BGN_PER_KILOWATT_HOUR, VAT_RATE, DOMAIN, PROVIDER_PRICES_BY_DATE


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Initialize bg_electricity_regulated_pricing config entry."""
    name = config_entry.title
    unique_id = config_entry.entry_id

    tariff_type = config_entry.options[CONF_TARIFF_TYPE]
    clock_offset = config_entry.options[CONF_CLOCK_OFFSET]
    provider = config_entry.options[CONF_PROVIDER]
    if provider == "custom":
        def price_provider_fun(x):
            if x == "day":
                return config_entry.options[CONF_CUSTOM_DAY_PRICE]
            else:
                return config_entry.options[CONF_CUSTOM_NIGHT_PRICE]
    else:
        def price_provider_fun(x):
            price = 0
            fees = 0
            for pp in PROVIDER_PRICES_BY_DATE:
                price = pp["prices"][provider][x]
                fees = pp["prices"][provider]["fees"]
                if "until" in pp and now_utc().timestamp() < pp["until"]:
                    break
            return (price + fees) * (1 + VAT_RATE)

    price_provider = BgElectricityRegulatedPricingProvider(tariff_type, clock_offset,
                                                           price_provider_fun)

    desc_price = SensorEntityDescription(
        key="price",
        translation_key="price",
        icon="mdi:currency-eur",
        native_unit_of_measurement=BGN_PER_KILOWATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=6,
        has_entity_name=True,
    )

    desc_tariff = SensorEntityDescription(
        key="tariff",
        translation_key="tariff",
        icon="mdi:clock-time-ten",
        has_entity_name=True,
    )

    async_add_entities([
        BgElectricityRegulatedPricingPriceSensorEntity(price_provider, unique_id,
                                                       name, desc_price),
        BgElectricityRegulatedPricingTariffSensorEntity(price_provider, unique_id,
                                                        name, desc_tariff)
    ])


def now_utc():
    return utcnow()


class BgElectricityRegulatedPricingSensorEntity(SensorEntity):
    """BgElectricityRegulatedPricing Sensor base."""

    def __init__(self, price_provider: BgElectricityRegulatedPricingProvider,
                 unique_id: str, name: str,
                 description: SensorEntityDescription) -> None:
        super().__init__()
        self.entity_description = description
        self._attr_unique_id = unique_id + "_" + description.key
        self._price_provider = price_provider
        self._device_name = name
        self._attr_device_info = DeviceInfo(
            name=name,
            identifiers={(DOMAIN, unique_id)},
            entry_type=DeviceEntryType.SERVICE,
        )


class BgElectricityRegulatedPricingPriceSensorEntity(
    BgElectricityRegulatedPricingSensorEntity
):
    """BgElectricityRegulatedPricing Sensor for price."""

    def __init__(self, price_provider: BgElectricityRegulatedPricingProvider,
                 unique_id: str, name: str,
                 description: SensorEntityDescription) -> None:
        super().__init__(price_provider, unique_id, name, description)
        self.update()

    def update(self) -> None:
        self._attr_native_value = self._price_provider.price()


class BgElectricityRegulatedPricingTariffSensorEntity(
    BgElectricityRegulatedPricingSensorEntity
):
    """BgElectricityRegulatedPricing Sensor for tariff."""

    def __init__(self, price_provider: BgElectricityRegulatedPricingProvider,
                 unique_id: str, name: str,
                 description: SensorEntityDescription) -> None:
        super().__init__(price_provider, unique_id, name, description)
        self.update()

    def update(self):
        self._attr_native_value = self._price_provider.tariff()


class BgElectricityRegulatedPricingProvider:
    """Pricing provider aware of current tariff and price."""

    def __init__(self, tariff_type, clock_offset, price_provider):
        self._tariff_type = tariff_type
        self._clock_offset = clock_offset
        self._price_provider = price_provider

    def tariff(self):
        # Get local time (includes daylight saving time if server is configured correctly)
        local_time = datetime.now()
    
        # Determine seasonal tariff window
        year = local_time.year
        summer_start = datetime(year, 4, 1)
        summer_end = datetime(year, 10, 31, 23, 59)
    
        if summer_start <= local_time <= summer_end:
            # Summer period: night is from 23:00 to 07:00
            night_start = 23 * 60
            night_end = 7 * 60
        else:
            # Winter period: night is from 22:00 to 06:00
            night_start = 22 * 60
            night_end = 6 * 60
    
        # Time in minutes since midnight, adjusted by optional clock offset
        hour_minutes = (local_time.hour * 60 + local_time.minute + self._clock_offset) % 1440
    
        if self._tariff_type == "dual":
            if night_start <= hour_minutes or hour_minutes < night_end:
                return "night"
        return "day"

    def price(self):
        return self._price_provider(self.tariff())
