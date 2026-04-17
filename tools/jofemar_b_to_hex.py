#!/usr/bin/env python3
"""
Конвертер прошивки Jofemar .b00/.b01 → Intel HEX для PIC24HJ256GP206.

Формат бинарника Jofemar:
  - Последовательные 24-битные инструкции PIC24
  - Каждое слово хранится как 4 байта: [low, mid, high, phantom(0x00)]
  - Файл покрывает всю program flash: 0x000000–0x02ABFE (PC-адреса)
  - Размер файла: 87552 слов × 4 = 350208 байт

Intel HEX для PIC24 (конвенция Microchip / MPLAB IPE):
  - Byte address = PC_address × 2  (т.е. word_index × 4)
  - Каждое инструкционное слово = 4 байта (3 инструкции + 1 phantom)
  - Extended Linear Address records (type 04) для адресов > 0xFFFF
"""

import sys
import os


def ihex_checksum(data_bytes: list[int]) -> int:
    """Two's complement checksum для Intel HEX."""
    return (~sum(data_bytes) + 1) & 0xFF


def make_record(byte_count: int, address: int, rec_type: int, data: bytes) -> str:
    """Собрать одну строку Intel HEX."""
    fields = [
        byte_count,
        (address >> 8) & 0xFF,
        address & 0xFF,
        rec_type,
    ]
    fields.extend(data)
    cs = ihex_checksum(fields)
    return ':' + ''.join(f'{b:02X}' for b in fields) + f'{cs:02X}'


def make_ela_record(upper16: int) -> str:
    """Extended Linear Address record (type 04)."""
    data = bytes([(upper16 >> 8) & 0xFF, upper16 & 0xFF])
    return make_record(2, 0x0000, 0x04, data)


def convert(input_path: str, output_path: str) -> None:
    with open(input_path, 'rb') as f:
        raw = f.read()

    file_size = len(raw)
    num_words = file_size // 4
    last_pc = (num_words - 1) * 2

    print(f"  Файл:        {input_path}")
    print(f"  Размер:      {file_size} байт  ({num_words} инструкций)")
    print(f"  PC-диапазон: 0x000000 – 0x{last_pc:06X}")

    # --- Найти реальный конец данных (пропустить trailing 0xFF) ---
    last_non_ff = file_size - 1
    while last_non_ff >= 0 and raw[last_non_ff] == 0xFF:
        last_non_ff -= 1
    # Выровнять вверх до границы 4-байтного слова
    effective_end = ((last_non_ff // 4) + 1) * 4
    used_words = effective_end // 4
    print(f"  Используется: {used_words} слов из {num_words}"
          f"  ({100 * used_words / num_words:.1f}%)")

    BYTES_PER_LINE = 16  # стандарт Intel HEX
    records: list[str] = []
    current_ela: int | None = None
    skipped_ff = 0

    offset = 0
    while offset < effective_end:
        # byte-адрес в HEX = offset  (т.к. в файле уже 4 байта на слово)
        byte_addr = offset

        # Extended Linear Address при смене верхних 16 бит
        ela = (byte_addr >> 16) & 0xFFFF
        if ela != current_ela:
            records.append(make_ela_record(ela))
            current_ela = ela

        addr16 = byte_addr & 0xFFFF

        # Размер чанка: до 16 байт, не пересекая 64KB-границу
        remaining_seg = 0x10000 - addr16
        chunk_size = min(BYTES_PER_LINE, effective_end - offset, remaining_seg)

        chunk = raw[offset:offset + chunk_size]

        # Пропускать чисто FF-блоки (стёртый flash)
        if all(b == 0xFF for b in chunk):
            skipped_ff += chunk_size
            offset += chunk_size
            continue

        records.append(make_record(len(chunk), addr16, 0x00, chunk))
        offset += chunk_size

    # EOF record
    records.append(':00000001FF')

    with open(output_path, 'w', newline='\n') as f:
        f.write('\n'.join(records) + '\n')

    hex_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    print(f"  Выход:       {output_path}")
    print(f"  Записей:     {len(records)}  "
          f"(пропущено {skipped_ff} байт пустого flash)")
    print(f"  Размер HEX:  {hex_size} байт")


def main() -> None:
    if len(sys.argv) < 2:
        print("Использование: python3 jofemar_b_to_hex.py <file.b00> [file.b01 ...]")
        print()
        print("Конвертирует бинарную прошивку Jofemar в Intel HEX")
        print("для программирования PIC24HJ256GP206 через MPLAB IPE + PICkit.")
        sys.exit(1)

    for path in sys.argv[1:]:
        if not os.path.isfile(path):
            print(f"ОШИБКА: файл не найден: {path}")
            continue
        base = os.path.basename(path)
        name, ext = os.path.splitext(base)
        # G501_F14.b00 → G501_F14_b00.hex
        bank = ext.lstrip('.')  # "b00" или "b01"
        out_dir = os.path.dirname(path) or '.'
        out = os.path.join(out_dir, f'{name}_{bank}.hex')
        print(f"\n{'='*60}")
        convert(path, out)

    print(f"\n{'='*60}")
    print("Готово. Откройте .hex в MPLAB IPE → File → Import.")
    print()
    print("ВАЖНО — Configuration Bits:")
    print("  В бинарнике НЕТ конфигурационных регистров PIC24")
    print("  (FOSCSEL, FOSC, FWDT, FPOR, FGS, FBS, FICD).")
    print("  Их нужно задать вручную в MPLAB IPE → Settings → ")
    print("  Configuration Bits, либо считать с рабочей платы.")
    print()
    print("  Типовые значения для Jofemar G-501 (HS crystal + PLL):")
    print("    FOSCSEL = 0x0003  (FNOSC=PRIPLL, IESO=OFF)")
    print("    FOSC    = 0x00E2  (FCKSM=CSDCMD, OSCIOFNC=OFF, POSCMD=HS)")
    print("    FWDT    = 0x005F  (FWDTEN=OFF — отключить WDT для теста)")
    print("    FPOR    = 0x0087  (defaults)")
    print("    FGS     = 0x0007  (GSS=OFF, GCP=OFF — без защиты)")
    print("    FBS     = 0x000F  (BSS=OFF, BWRP=OFF — без защиты)")
    print("    FICD    = 0x0003  (ICS=PGD1, JTAGEN=OFF)")


if __name__ == '__main__':
    main()
