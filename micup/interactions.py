"""Slash komutları, butonlar, seçim menüleri, modallar ve etkileşim yanıtları.

Micup etkileşimleri gateway üzerinden `INTERACTION_CREATE` olayı olarak iletir. Yanıtlar
Discord ile aynı rotalarla gönderilir (`/v1` önekiyle). Kurallar:

- İlk yanıt 3 saniye içinde verilmelidir. Uzun işlerde önce `defer()` çağır.
- Etkileşim tokenı 15 dakika geçerlidir. Sonraki yanıtlar için `edit()` ve `followup()` kullan.
- `ephemeral=True` yanıt yalnızca komutu kullanan kişiye görünür.
"""
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .models import Message, User

EPHEMERAL_FLAG = 64
MAX_CHOICES = 25
MAX_OPTIONS = 25
MAX_BUTTONS_PER_ROW = 5


class InteractionType:
    PING = 1
    APPLICATION_COMMAND = 2
    MESSAGE_COMPONENT = 3
    AUTOCOMPLETE = 4
    MODAL_SUBMIT = 5


class CallbackType:
    PONG = 1
    CHANNEL_MESSAGE = 4
    DEFERRED_CHANNEL_MESSAGE = 5
    DEFERRED_UPDATE_MESSAGE = 6
    UPDATE_MESSAGE = 7
    APPLICATION_COMMAND_AUTOCOMPLETE_RESULT = 8
    MODAL = 9


class ComponentType:
    ACTION_ROW = 1
    BUTTON = 2
    STRING_SELECT = 3
    TEXT_INPUT = 4


class ButtonStyle:
    PRIMARY = 1
    SECONDARY = 2
    SUCCESS = 3
    DANGER = 4
    LINK = 5


class TextInputStyle:
    SHORT = 1
    PARAGRAPH = 2


class OptionType:
    SUB_COMMAND = 1
    SUB_COMMAND_GROUP = 2
    STRING = 3
    INTEGER = 4
    BOOLEAN = 5
    USER = 6
    CHANNEL = 7
    ROLE = 8
    MENTIONABLE = 9
    NUMBER = 10
    ATTACHMENT = 11


_SUPPORTED_OPTION_TYPES = {1, 2, 3, 4, 5, 6, 7, 8, 10}


def _check_text(value: str, low: int, high: int, what: str) -> None:
    if not isinstance(value, str) or not (low <= len(value) <= high):
        raise ValueError(f"{what} {low}-{high} karakter olmalı.")


def option(
    name: str,
    description: str,
    type: int = OptionType.STRING,
    *,
    required: bool = False,
    choices: Optional[List[Dict[str, Any]]] = None,
    autocomplete: bool = False,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
) -> Dict[str, Any]:
    """Slash komutu parametresi.

    choices: [{"name": "Etiket", "value": "deger"}, ...] (en fazla 25)
    autocomplete: True ise yazarken `@bot.autocomplete(komut, parametre)` çağrılır. choices ile birlikte kullanılamaz.
    """
    _check_text(name, 1, 32, "Parametre adı")
    _check_text(description, 1, 100, "Parametre açıklaması")
    if type not in _SUPPORTED_OPTION_TYPES:
        raise ValueError(f"Desteklenmeyen parametre tipi: {type}. Mention (9) ve attachment (11) bu sürümde yok.")
    data: Dict[str, Any] = {"name": name, "description": description, "type": type, "required": required}
    if choices:
        if len(choices) > MAX_CHOICES:
            raise ValueError(f"En fazla {MAX_CHOICES} seçenek olabilir.")
        if autocomplete:
            raise ValueError("autocomplete ve choices birlikte kullanılamaz.")
        for ch in choices:
            _check_text(ch["name"], 1, 100, "Seçenek adı")
        data["choices"] = choices
    if autocomplete:
        if type not in (OptionType.STRING, OptionType.INTEGER, OptionType.NUMBER):
            raise ValueError("autocomplete yalnızca metin, tam sayı ve sayı parametrelerinde kullanılır.")
        data["autocomplete"] = True
    if min_value is not None and max_value is not None and min_value > max_value:
        raise ValueError("min_value, max_value'dan büyük olamaz.")
    if min_length is not None and max_length is not None and min_length > max_length:
        raise ValueError("min_length, max_length'ten büyük olamaz.")
    if min_value is not None:
        data["min_value"] = min_value
    if max_value is not None:
        data["max_value"] = max_value
    if min_length is not None:
        if not (0 <= min_length <= 6000):
            raise ValueError("min_length 0-6000 arasında olmalı.")
        data["min_length"] = min_length
    if max_length is not None:
        if not (1 <= max_length <= 6000):
            raise ValueError("max_length 1-6000 arasında olmalı.")
        data["max_length"] = max_length
    return data


def subcommand(name: str, description: str, options: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Alt komut. Üst slash komutunun `options` listesine konur."""
    _check_text(name, 1, 32, "Alt komut adı")
    _check_text(description, 1, 100, "Alt komut açıklaması")
    if options and len(options) > MAX_OPTIONS:
        raise ValueError(f"Bir alt komutta en fazla {MAX_OPTIONS} parametre olabilir.")
    data: Dict[str, Any] = {"name": name, "description": description, "type": OptionType.SUB_COMMAND}
    if options:
        data["options"] = list(options)
    return data


def subcommand_group(name: str, description: str, subcommands: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Alt komut grubu. İçinde 1-25 alt komut olmalı."""
    _check_text(name, 1, 32, "Grup adı")
    _check_text(description, 1, 100, "Grup açıklaması")
    if not (1 <= len(subcommands) <= MAX_OPTIONS):
        raise ValueError(f"Bir grupta 1-{MAX_OPTIONS} alt komut olmalı.")
    for sub in subcommands:
        if sub.get("type") != OptionType.SUB_COMMAND:
            raise ValueError("Grubun içine yalnızca subcommand() ile üretilen alt komutlar konur.")
    return {"name": name, "description": description, "type": OptionType.SUB_COMMAND_GROUP, "options": list(subcommands)}


def button(
    label: Optional[str] = None,
    *,
    custom_id: Optional[str] = None,
    style: int = ButtonStyle.PRIMARY,
    url: Optional[str] = None,
    disabled: bool = False,
    emoji: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Buton bileşeni. Link butonu için `style=ButtonStyle.LINK` ve `url`, diğerleri için `custom_id` ver."""
    if style == ButtonStyle.LINK:
        if not url:
            raise ValueError("Link butonu için url gerekli.")
        if custom_id:
            raise ValueError("Link butonunda custom_id olmaz.")
    else:
        if not custom_id:
            raise ValueError("Tıklanabilir butonda custom_id gerekli.")
        if url:
            raise ValueError("url yalnızca link butonunda kullanılır.")
    data: Dict[str, Any] = {"type": ComponentType.BUTTON, "style": style, "disabled": disabled}
    if label:
        data["label"] = label
    if custom_id:
        data["custom_id"] = custom_id
    if url:
        data["url"] = url
    if emoji:
        data["emoji"] = emoji
    return data


def select_option(
    label: str,
    value: str,
    *,
    description: Optional[str] = None,
    default: bool = False,
    emoji: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Seçim menüsündeki bir seçenek."""
    _check_text(label, 1, 100, "Seçenek etiketi")
    _check_text(value, 1, 100, "Seçenek değeri")
    data: Dict[str, Any] = {"label": label, "value": value, "default": default}
    if description:
        data["description"] = description
    if emoji:
        data["emoji"] = emoji
    return data


def select_menu(
    custom_id: str,
    options: List[Dict[str, Any]],
    *,
    placeholder: Optional[str] = None,
    min_values: int = 1,
    max_values: int = 1,
    disabled: bool = False,
) -> Dict[str, Any]:
    """Metin seçim menüsü. options: select_option(...) çıktıları (1-25 adet)."""
    _check_text(custom_id, 1, 100, "custom_id")
    if not (1 <= len(options) <= MAX_CHOICES):
        raise ValueError(f"Menüde 1-{MAX_CHOICES} seçenek olmalı.")
    if not (0 <= min_values <= max_values <= len(options)):
        raise ValueError("min_values ve max_values seçenek sayısıyla uyumlu olmalı.")
    data: Dict[str, Any] = {
        "type": ComponentType.STRING_SELECT,
        "custom_id": custom_id,
        "options": list(options),
        "min_values": min_values,
        "max_values": max_values,
        "disabled": disabled,
    }
    if placeholder:
        data["placeholder"] = placeholder
    return data


def text_input(
    custom_id: str,
    label: str,
    *,
    style: int = TextInputStyle.SHORT,
    required: bool = True,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
    placeholder: Optional[str] = None,
    value: Optional[str] = None,
) -> Dict[str, Any]:
    """Modal içindeki metin alanı. Her alan ayrı bir action_row içinde olmalı (modal() bunu yapar)."""
    _check_text(custom_id, 1, 100, "custom_id")
    _check_text(label, 1, 45, "Alan etiketi")
    data: Dict[str, Any] = {
        "type": ComponentType.TEXT_INPUT,
        "custom_id": custom_id,
        "label": label,
        "style": style,
        "required": required,
    }
    if min_length is not None:
        data["min_length"] = min_length
    if max_length is not None:
        data["max_length"] = max_length
    if placeholder:
        data["placeholder"] = placeholder
    if value:
        data["value"] = value
    return data


def modal(custom_id: str, title: str, fields: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Modal gövdesi. fields: text_input(...) çıktıları (1-5 adet). Her alan kendi satırına konur."""
    _check_text(custom_id, 1, 100, "custom_id")
    _check_text(title, 1, 45, "Modal başlığı")
    if not (1 <= len(fields) <= 5):
        raise ValueError("Modalda 1-5 alan olmalı.")
    rows = [{"type": ComponentType.ACTION_ROW, "components": [f]} for f in fields]
    return {"custom_id": custom_id, "title": title, "components": rows}


def action_row(*components: Dict[str, Any]) -> Dict[str, Any]:
    """Butonları ya da seçim menüsünü bir satırda toplar. Bir satırda en fazla 5 buton olabilir."""
    if not components:
        raise ValueError("Satır boş olamaz.")
    if len(components) > MAX_BUTTONS_PER_ROW:
        raise ValueError(f"Bir satırda en fazla {MAX_BUTTONS_PER_ROW} bileşen olabilir.")
    return {"type": ComponentType.ACTION_ROW, "components": list(components)}


def _split_options(raw: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str], List[Dict[str, Any]]]:
    """Ham seçenek listesinden (grup, alt komut, düz parametreler) çıkarır."""
    group = sub = None
    flat = list(raw or [])
    if flat and flat[0].get("type") == OptionType.SUB_COMMAND_GROUP:
        group = flat[0]["name"]
        flat = list(flat[0].get("options") or [])
    if flat and flat[0].get("type") == OptionType.SUB_COMMAND:
        sub = flat[0]["name"]
        flat = list(flat[0].get("options") or [])
    return group, sub, flat


class Interaction:
    """Bir slash komut, buton, seçim menüsü, modal ya da otomatik tamamlama etkileşimi."""

    def __init__(self, data: Dict[str, Any], bot: Any):
        self._bot = bot
        self.raw = data
        self.id: str = data["id"]
        self.token: str = data["token"]
        self.type: int = int(data.get("type", 0))
        self.application_id: Optional[str] = data.get("application_id")
        self.guild_id: Optional[str] = data.get("guild_id")
        self.channel_id: Optional[str] = data.get("channel_id")
        member = data.get("member")
        user_data = (member or {}).get("user") or data.get("user") or {}
        self.member: Optional[Dict[str, Any]] = member
        self.user = User(user_data)
        self.data: Dict[str, Any] = data.get("data") or {}

        self.command_name: Optional[str] = None
        self.subcommand_group: Optional[str] = None
        self.subcommand: Optional[str] = None
        self.options: Dict[str, Any] = {}
        self.focused: Optional[Tuple[str, Any]] = None
        self.resolved: Dict[str, Any] = self.data.get("resolved") or {}
        self._raw_options: List[Dict[str, Any]] = []

        if self.type in (InteractionType.APPLICATION_COMMAND, InteractionType.AUTOCOMPLETE):
            self.command_name = self.data.get("name")
            group, sub, flat = _split_options(self.data.get("options") or [])
            self.subcommand_group, self.subcommand = group, sub
            self._raw_options = flat
            for opt in flat:
                if "value" in opt:
                    self.options[opt["name"]] = opt["value"]
                if opt.get("focused"):
                    self.focused = (opt["name"], opt.get("value"))

        self.custom_id: Optional[str] = self.data.get("custom_id")
        self.component_type: Optional[int] = self.data.get("component_type")
        self.values: List[str] = list(self.data.get("values") or [])
        self.message: Optional[Message] = Message(data["message"], bot) if data.get("message") else None
        self.modal_values: Dict[str, str] = {}
        if self.type == InteractionType.MODAL_SUBMIT:
            for row in self.data.get("components") or []:
                for comp in row.get("components") or []:
                    if "custom_id" in comp:
                        self.modal_values[comp["custom_id"]] = comp.get("value", "")

        self._responded = False

    @property
    def is_command(self) -> bool:
        return self.type == InteractionType.APPLICATION_COMMAND

    @property
    def is_button(self) -> bool:
        return self.type == InteractionType.MESSAGE_COMPONENT and self.component_type == ComponentType.BUTTON

    @property
    def is_select(self) -> bool:
        return self.type == InteractionType.MESSAGE_COMPONENT and self.component_type == ComponentType.STRING_SELECT

    @property
    def is_modal_submit(self) -> bool:
        return self.type == InteractionType.MODAL_SUBMIT

    @property
    def is_autocomplete(self) -> bool:
        return self.type == InteractionType.AUTOCOMPLETE

    @property
    def responded(self) -> bool:
        return self._responded

    def resolved_option(self, name: str) -> Optional[Dict[str, Any]]:
        """Kullanıcı, kanal, rol ya da ek parametrelerinin çözümlenmiş ham verisi."""
        for opt in self._raw_options:
            if opt.get("name") == name and "value" in opt:
                key = str(opt["value"])
                for bucket in ("users", "members", "channels", "roles", "attachments"):
                    found = (self.resolved.get(bucket) or {}).get(key)
                    if found is not None:
                        return found
        return None

    def user_option(self, name: str) -> Optional[User]:
        """Kullanıcı parametresini User olarak döner."""
        data = self.resolved_option(name)
        return User(data) if data else None

    def _app_id(self) -> str:
        app = self.application_id or self._bot.application_id
        if not app:
            raise RuntimeError("Uygulama kimliği bilinmiyor. Bot henüz hazır değil.")
        return app

    @staticmethod
    def _message_data(
        content: Optional[str] = None,
        *,
        embeds: Optional[List[Dict[str, Any]]] = None,
        components: Optional[List[Dict[str, Any]]] = None,
        ephemeral: bool = False,
        **fields: Any,
    ) -> Dict[str, Any]:
        data: Dict[str, Any] = {k: v for k, v in fields.items() if v is not None}
        if content is not None:
            data["content"] = content
        if embeds is not None:
            data["embeds"] = embeds
        if components is not None:
            data["components"] = components
        if ephemeral:
            data["flags"] = EPHEMERAL_FLAG
        data.setdefault("allowed_mentions", {"parse": []})
        return data

    async def _callback(self, callback_type: int, data: Optional[Dict[str, Any]] = None) -> None:
        body: Dict[str, Any] = {"type": callback_type}
        if data is not None:
            body["data"] = data
        await self._bot._request("POST", f"/v1/interactions/{self.id}/{self.token}/callback", json=body)
        self._responded = True

    def _ensure_unanswered(self) -> None:
        if self._responded:
            raise RuntimeError("Bu etkileşime zaten yanıt verildi. Sonrası için edit() ya da followup() kullan.")

    async def respond(
        self,
        content: Optional[str] = None,
        *,
        embeds: Optional[List[Dict[str, Any]]] = None,
        components: Optional[List[Dict[str, Any]]] = None,
        ephemeral: bool = False,
        **fields: Any,
    ) -> None:
        """İlk yanıtı yeni bir mesaj olarak gönderir. Gizli olabilir (`ephemeral=True`)."""
        self._ensure_unanswered()
        data = self._message_data(content, embeds=embeds, components=components, ephemeral=ephemeral, **fields)
        await self._callback(CallbackType.CHANNEL_MESSAGE, data)

    async def defer(self, ephemeral: bool = False) -> None:
        """'Düşünüyor' yanıtı verir. 3 saniye sınırını aşmamak için kullan, sonra edit() ile doldur."""
        self._ensure_unanswered()
        data = {"flags": EPHEMERAL_FLAG} if ephemeral else None
        await self._callback(CallbackType.DEFERRED_CHANNEL_MESSAGE, data)

    async def defer_update(self) -> None:
        """Buton ya da seçim mesajını değiştirmeden sessizce onaylar."""
        self._ensure_unanswered()
        if not (self.is_button or self.is_select):
            raise RuntimeError("defer_update yalnızca buton ve seçim menüsü etkileşimlerinde kullanılır.")
        await self._callback(CallbackType.DEFERRED_UPDATE_MESSAGE)

    async def update(
        self,
        content: Optional[str] = None,
        *,
        embeds: Optional[List[Dict[str, Any]]] = None,
        components: Optional[List[Dict[str, Any]]] = None,
        **fields: Any,
    ) -> None:
        """Buton ya da seçim menüsünün bulunduğu mesajı yeniden yazar."""
        self._ensure_unanswered()
        if not (self.is_button or self.is_select):
            raise RuntimeError("update yalnızca buton ve seçim menüsü etkileşimlerinde kullanılır. Komutlarda respond() kullan.")
        data = self._message_data(content, embeds=embeds, components=components, **fields)
        await self._callback(CallbackType.UPDATE_MESSAGE, data)

    async def show_modal(self, modal_data: Dict[str, Any]) -> None:
        """Bir modal açar. modal_data: modal(custom_id, title, fields) çıktısı."""
        self._ensure_unanswered()
        if self.is_autocomplete or self.is_modal_submit:
            raise RuntimeError("Modal yalnızca komut, buton ya da seçim menüsü etkileşiminde açılabilir.")
        await self._callback(CallbackType.MODAL, dict(modal_data))

    async def respond_choices(self, choices: List[Dict[str, Any]]) -> None:
        """Otomatik tamamlama önerilerini gönderir (en fazla 25)."""
        self._ensure_unanswered()
        if not self.is_autocomplete:
            raise RuntimeError("respond_choices yalnızca otomatik tamamlama etkileşiminde kullanılır.")
        if len(choices) > MAX_CHOICES:
            raise ValueError(f"En fazla {MAX_CHOICES} öneri gönderilebilir.")
        await self._callback(CallbackType.APPLICATION_COMMAND_AUTOCOMPLETE_RESULT, {"choices": list(choices)})

    async def edit(
        self,
        content: Optional[str] = None,
        *,
        embeds: Optional[List[Dict[str, Any]]] = None,
        components: Optional[List[Dict[str, Any]]] = None,
        **fields: Any,
    ) -> Message:
        """İlk yanıtı (defer ya da respond sonrası) düzenler. 15 dakika içinde çalışır."""
        data = self._message_data(content, embeds=embeds, components=components, **fields)
        result = await self._bot._request(
            "PATCH",
            f"/v1/webhooks/{self._app_id()}/{self.token}/messages/@original",
            json=data,
        )
        return Message(result, self._bot)

    async def get_original(self) -> Message:
        """İlk yanıt mesajını okur."""
        result = await self._bot._request(
            "GET", f"/v1/webhooks/{self._app_id()}/{self.token}/messages/@original"
        )
        return Message(result, self._bot)

    async def delete_original(self) -> None:
        """İlk yanıt mesajını siler."""
        await self._bot._request(
            "DELETE", f"/v1/webhooks/{self._app_id()}/{self.token}/messages/@original"
        )

    async def followup(
        self,
        content: Optional[str] = None,
        *,
        embeds: Optional[List[Dict[str, Any]]] = None,
        components: Optional[List[Dict[str, Any]]] = None,
        ephemeral: bool = False,
        **fields: Any,
    ) -> Message:
        """Takip mesajı gönderir. 15 dakika içinde en fazla 20 takip yapılabilir."""
        data = self._message_data(content, embeds=embeds, components=components, ephemeral=ephemeral, **fields)
        result = await self._bot._request(
            "POST",
            f"/v1/interactions/{self.id}/followups",
            json=data,
            extra_headers={"Idempotency-Key": uuid.uuid4().hex},
        )
        return Message(result, self._bot)

    async def edit_followup(
        self,
        message_id: str,
        content: Optional[str] = None,
        *,
        embeds: Optional[List[Dict[str, Any]]] = None,
        components: Optional[List[Dict[str, Any]]] = None,
        **fields: Any,
    ) -> Message:
        """Bir takip mesajını düzenler."""
        data = self._message_data(content, embeds=embeds, components=components, **fields)
        result = await self._bot._request(
            "PATCH",
            f"/v1/webhooks/{self._app_id()}/{self.token}/messages/{message_id}",
            json=data,
        )
        return Message(result, self._bot)

    async def delete_followup(self, message_id: str) -> None:
        """Bir takip mesajını siler."""
        await self._bot._request(
            "DELETE", f"/v1/webhooks/{self._app_id()}/{self.token}/messages/{message_id}"
        )
