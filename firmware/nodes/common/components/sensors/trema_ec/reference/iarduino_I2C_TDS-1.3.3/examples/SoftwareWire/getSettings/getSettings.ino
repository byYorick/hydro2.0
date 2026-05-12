// ПРИМЕР ПОЛУЧЕНИЯ НАСТРОЕК МОДУЛЯ:                         // * Строки со звёздочкой являются необязательными.
// Требуется установить библиотеку <iarduino_I2C_Software.h> //   https://iarduino.ru/file/627.html
                                                             //
// TDS/EC-метр с щупом (Trema-модуль) Flash-I2C:             //   https://iarduino.ru/shop/Sensory-Datchiki/bamper-s-9-datchikami-liniy-s-shagom-7mm-flash-i2c.html
// Информация о подключении модулей к шине I2C:              //   https://wiki.iarduino.ru/page/i2c_connection/
// Информация о модуле и описание библиотеки:                //   https://wiki.iarduino.ru/page/TDS-EC-i2c/
                                                             //
#include <iarduino_I2C_Software.h>                           //   Подключаем библиотеку для работы с программной шиной I2C, до подключения библиотеки iarduino_I2C_TDS.
SoftTwoWire sWire(3,4);                                      //   Создаём объект программной шины I2C указав выводы которым будет назначена роль линий: SDA, SCL.
                                                             //
#include <iarduino_I2C_TDS.h>                                //   Подключаем библиотеку для работы с TDS/EC-метром I2C-flash.
iarduino_I2C_TDS tds(0x09);                                  //   Объявляем объект tds  для работы с функциями и методами библиотеки iarduino_I2C_TDS, указывая адрес модуля на шине I2C.
                                                             //   Если объявить объект без указания адреса (iarduino_I2C_TDS tds;), то адрес будет найден автоматически.
void setup(){                                                //
     delay(500);                                             // * Ждём завершение переходных процессов связанных с подачей питания.
     Serial.begin(9600);                                     //   Инициируем работу с шиной UART для передачи данных в монитор последовательного порта на скорости 9600 бит/сек.
     tds.begin(&sWire);                                      //   Инициируем работу с TDS/EC-метром, указав ссылку на объект для работы с шиной I2C на которой находится модуль (по умолчанию &Wire).
     Serial.print("F    = "         );                       //
     Serial.print(tds.getFrequency());                       //   Выводим частоту переменного тока используемую для измерений от 50 до 500 Гц.
     Serial.print("Гц.\r\nTDS1 = "  );                       //
     Serial.print(tds.getKnownTDS(1));                       //   Выводим требуемую концентрацию 1 раствора для калибровки модуля кнопкой от 0 до 10'000 ppm.
     Serial.print("ppm.\r\nTDS2 = " );                       //
     Serial.print(tds.getKnownTDS(2));                       //   Выводим требуемую концентрацию 2 раствора для калибровки модуля кнопкой от 0 до 10'000 ppm.
     Serial.print("ppm.\r\nKt   = " );                       //
     Serial.print(tds.getKt()     ,4);                       //   Выводим температурный коэффициент жидкости от 0,0000 до 6,5535.
     Serial.print("\r\nKp   = "     );                       //
     Serial.print(tds.getKp()     ,2);                       //   Выводим коэффициент пересчёта от 0,01 до 2,55.
     Serial.print("\r\nT    = "     );                       //
     Serial.print(tds.get_T()     ,2);                       //   Выводим опорную температуру жидкости от 0,00 до 63,75 °С.
     Serial.print("°С.\r\nKa   = "  );                       //
     Serial.print(tds.getKa()     ,1);                       //   Выводим множитель степеной функции от 0,1 до 1'677'721,5.
     Serial.print(".\r\nKb   = "    );                       //
     Serial.print(tds.getKb()     ,3);                       //   Выводим степень степенной функции от -0,010 до -65,535.
     Serial.print(".\r\n"           );                       //
}                                                            //
                                                             //
void loop(){}                                                //