package com.hydro.app.core.json

import com.squareup.moshi.JsonAdapter
import com.squareup.moshi.JsonReader
import com.squareup.moshi.JsonWriter
import com.squareup.moshi.Moshi
import com.squareup.moshi.Types
import java.lang.reflect.Type

/**
 * Laravel иногда отдаёт decimal как строку (`"6.4200"`). Адаптер принимает и число, и строку.
 */
object LenientNumberAdapters : JsonAdapter.Factory {
    override fun create(type: Type, annotations: Set<Annotation>, moshi: Moshi): JsonAdapter<*>? {
        if (annotations.isNotEmpty()) return null
        return when (Types.getRawType(type)) {
            java.lang.Double::class.java, Double::class.javaPrimitiveType -> LenientDoubleAdapter
            java.lang.Long::class.java, Long::class.javaPrimitiveType -> LenientLongAdapter
            java.lang.Integer::class.java, Int::class.javaPrimitiveType -> LenientIntAdapter
            else -> null
        }
    }
}

private object LenientDoubleAdapter : JsonAdapter<Double>() {
    override fun fromJson(reader: JsonReader): Double? = readNumber(reader)?.toDouble()

    override fun toJson(writer: JsonWriter, value: Double?) {
        if (value == null) writer.nullValue() else writer.value(value)
    }
}

private object LenientLongAdapter : JsonAdapter<Long>() {
    override fun fromJson(reader: JsonReader): Long? = readNumber(reader)?.toLong()

    override fun toJson(writer: JsonWriter, value: Long?) {
        if (value == null) writer.nullValue() else writer.value(value)
    }
}

private object LenientIntAdapter : JsonAdapter<Int>() {
    override fun fromJson(reader: JsonReader): Int? = readNumber(reader)?.toInt()

    override fun toJson(writer: JsonWriter, value: Int?) {
        if (value == null) writer.nullValue() else writer.value(value)
    }
}

private fun readNumber(reader: JsonReader): Double? {
    return when (reader.peek()) {
        JsonReader.Token.NULL -> {
            reader.nextNull<Any>()
            null
        }
        JsonReader.Token.NUMBER -> reader.nextDouble()
        JsonReader.Token.STRING -> reader.nextString().trim().toDoubleOrNull()
        else -> {
            reader.skipValue()
            null
        }
    }
}
