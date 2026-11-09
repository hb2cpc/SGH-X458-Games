
"""Offline ARM oracle used to compare the extracted source port."""

from importlib import import_module

from unicorn import UC_ARCH_ARM, UC_HOOK_CODE, UC_HOOK_MEM_INVALID, UC_MODE_THUMB, Uc, UcError
from unicorn.arm_const import (
    UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP,
)

from handset.session import Session

from .firmware import GAME_ENTRY, ROM_END, load_rom


layout = import_module("X-Fighter.layout")


RAM = 0x01000000
STACK = 0x013FF000
RETURN_PC = 0x013FF800


class FirmwareGame(Session):
    instruction_limit = 2_000_000

    def __init__(self, rom=None, language=1, on_audio=None, save=None):
        super().__init__(language, on_audio, save)
        self.rom = rom if rom is not None else load_rom()
        self.cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
        self.cpu.mem_map(0, (ROM_END + 4095) & ~4095)
        self.cpu.mem_write(0, self.rom)
        self.cpu.mem_map(RAM, 0x400000)
        self.initialize_ram()
        self.failed_access = None
        self.returned = False
        self.hooks = {
            **self.devices,
            RETURN_PC: self.return_to_host,
            0x22815E: self.no_device_action,
            0x2283A0: self.no_device_action,
            0x2283AC: self.no_device_action,
            0x262954: self.memset,
            0x262998: self.memcpy,
        }
        for address in self.hooks:
            self.cpu.hook_add(UC_HOOK_CODE, self.dispatch_hook, begin=address, end=address)
        self.cpu.hook_add(UC_HOOK_MEM_INVALID, self.invalid_access)

    def call(self, address, a=0, b=0, c=0):
        self.returned = False
        self.failed_access = None
        self.cpu.reg_write(UC_ARM_REG_SP, STACK)
        self.cpu.reg_write(UC_ARM_REG_LR, RETURN_PC | 1)
        self.cpu.reg_write(UC_ARM_REG_R0, a)
        self.cpu.reg_write(UC_ARM_REG_R1, b)
        self.cpu.reg_write(UC_ARM_REG_R2, c)
        try:
            self.cpu.emu_start(address, 0, count=self.instruction_limit)
        except UcError as error:
            pc = self.cpu.reg_read(UC_ARM_REG_PC)
            lr = self.cpu.reg_read(UC_ARM_REG_LR)
            raise RuntimeError(f"Firmware stopped at {pc:#x} (LR {lr:#x}, access {self.failed_access})") from error
        if not self.returned:
            raise RuntimeError(f"Firmware did not return from {address:#x} at PC {self.cpu.reg_read(UC_ARM_REG_PC):#x}")
        return self.cpu.reg_read(UC_ARM_REG_R0)

    def event(self, kind, value=0):
        return self.call(self.event_entry, kind, value)

    def read(self, address, size):
        return bytes(self.cpu.mem_read(address, size))

    def write(self, address, data):
        self.cpu.mem_write(address, data)

    def dispatch_hook(self, cpu, address, _size, _user):
        link = cpu.reg_read(UC_ARM_REG_LR)
        result = self.hooks[address](cpu.reg_read(UC_ARM_REG_R0), cpu.reg_read(UC_ARM_REG_R1),
                                     cpu.reg_read(UC_ARM_REG_R2), link)
        if address != RETURN_PC:
            if result is not None:
                cpu.reg_write(UC_ARM_REG_R0, result)
            cpu.reg_write(UC_ARM_REG_PC, link)

    def invalid_access(self, _cpu, access, address, size, _value, _user):
        self.failed_access = (access, hex(address), size)
        return False

    def return_to_host(self, *_):
        self.returned = True
        self.cpu.emu_stop()

    def memcpy(self, dest, source, length, _):
        if length:
            self.write(dest, self.read(source, length))
        return dest

    def memset(self, dest, value, length, _):
        if length:
            self.write(dest, bytes((value & 255,)) * length)
        return dest

    @staticmethod
    def no_device_action(*_):
        return 0


class Game(FirmwareGame):
    game_index = 0
    event_entry = GAME_ENTRY
    manifest_path = layout.MANIFEST
    state_address = layout.STATE
    battle_key_address = layout.BATTLE_KEY
