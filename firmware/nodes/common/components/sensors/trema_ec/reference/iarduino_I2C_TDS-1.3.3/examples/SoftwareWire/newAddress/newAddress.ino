// ПРИМЕР СМЕНЫ АДРЕСА МОДУЛЯ:                               // * Строки со звёздочкой являются необязательными.
// Требуется установить библиотеку <iarduino_I2C_Software.h> //   https://iarduino.ru/file/627.html
                                                             //
// TDS/EC-метр с щупом (Trema-модуль) Flash-I2C:             //   https://iarduino.ru/shop/Sensory-Datchiki/bamper-s-9-datchikami-liniy-s-shagom-7mm-flash-i2c.html
// Информация о подключении модулей к шине I2C:              //   https://wiki.iarduino.ru/page/i2c_connection/
// Информация о модуле и описание библиотеки:                //   https://wiki.iarduino.ru/page/TDS-EC-i2c/
                                                             //
// Данный скетч демонстрирует не только                      //
// возможность смены адреса на указанный в                   //
// переменной newAddress, но и обнаружение,                  //
// и вывод текущего адреса модуля на шине I2C.               //
                                                             //
// Библиотека <iarduino_I2C_TDS.h> предназначена             //
// для работы с TDS/EC-метрами I2C-flash                     //
// и меняет только их адреса.                                //
// Но, в разделе Файл/Примеры/.../findSortDevices            //
// находятся примеры смены и сортировки адресов              //
// любых модулей iarduino серии Flash I2C.                   //
                                                             //
uint8_t newAddress = 0x09;                                   //   Назначаемый модулю адрес (0x07 < адрес < 0x7F).
                                                             //
#include <iarduino_I2C_Software.h>                           //   Подключаем библиотеку для работы с программной шиной I2C, до подключения библиотеки iarduino_I2C_TDS.
SoftTwoWire sWire(3,4);                                      //   Создаём объект программной шины I2C указав выводы которым будет назначена роль линий: SDA, SCL.
                                                             //
#include <iarduino_I2C_TDS.h>                                //   Подключаем библиотеку для работы с TDS/EC-метром I2C-flash.
iarduino_I2C_TDS tds;                                        //   Объявляем объект tds  для работы с функциями и методами библиотеки iarduino_I2C_TDS.
                                                             //   Если при объявлении объекта указать адрес, например, iarduino_I2C_TDS tds(0xBB), то пример будет работать с тем модулем, адрес которого был указан.
void setup(){                                                //
    delay(500);                                              // * Ждём завершение переходных процессов связанных с подачей питания.
    Serial.begin(9600);                                      //
    while(!Serial){;}                                        // * Ждём завершения инициализации шины UART.
    if( tds.begin(&sWire) ){                                 //   Инициируем работу с модулем, указав ссылку на объект для работы с шиной I2C на которой находится модуль (Wire, Wire1, Wire2 ...).
        Serial.print("Найден модуль 0x");                    //
        Serial.println( tds.getAddress(), HEX );             //   Выводим текущий адрес модуля.
        if( tds.changeAddress(newAddress) ){                 //   Меняем адрес модуля на newAddress.
            Serial.print("Адрес изменён на 0x");             //
            Serial.println(tds.getAddress(),HEX);            //   Выводим текущий адрес модуля.
        }else{                                               //
            Serial.println("Адрес не изменён!");             //
        }                                                    //
    }else{                                                   //
        Serial.println("Модуль не найден!");                 //
    }                                                        //
}                                                            //
                                                             //
void loop(){                                                 //
}                                                            //
