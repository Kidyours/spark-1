#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import sys
from typing import cast, overload, Dict, Iterable, List, Optional, Tuple, TYPE_CHECKING, Union

from py4j.java_gateway import JavaClass, JavaObject  # type: ignore[import]

from pyspark import RDD, since
from pyspark.sql.column import _to_seq, _to_java_column, Column
from pyspark.sql.types import StructType
from pyspark.sql import utils
from pyspark.sql.utils import to_str

if TYPE_CHECKING:
    from pyspark.sql._typing import OptionalPrimitiveType, ColumnOrName
    from pyspark.sql.session import SparkSession
    from pyspark.sql.dataframe import DataFrame
    from pyspark.sql.streaming import StreamingQuery

__all__ = ["DataFrameReader", "DataFrameWriter"]

PathOrPaths = Union[str, List[str]]
TupleOrListOfString = Union[List[str], Tuple[str, ...]]


class OptionUtils:
    def _set_opts(
        self,
        schema: Optional[Union[StructType, str]] = None,
        **options: "OptionalPrimitiveType",
    ) -> None:
        """
        Set named options (filter out those the value is None)
        """
        if schema is not None:
            self.schema(schema)  # type: ignore[attr-defined]
        for k, v in options.items():
            if v is not None:
                self.option(k, v)  # type: ignore[attr-defined]


class DataFrameReader(OptionUtils):
    """
    Interface used to load a :class:`DataFrame` from external storage systems
    (e.g. file systems, key-value stores, etc). Use :attr:`SparkSession.read`
    to access this.

    .. versionadded:: 1.4
    """

    def __init__(self, spark: "SparkSession"):
        self._jreader = spark._jsparkSession.read()  # type: ignore[attr-defined]
        self._spark = spark

    def _df(self, jdf: JavaObject) -> "DataFrame":
        from pyspark.sql.dataframe import DataFrame

        return DataFrame(jdf, self._spark)

    def format(self, source: str) -> "DataFrameReader":
        """Specifies the input data source format.

        .. versionadded:: 1.4.0

        Parameters
        ----------
        source : str
            string, name of the data source, e.g. 'json', 'parquet'.

        Examples
        --------
        >>> df = spark.read.format('json').load('python/test_support/sql/people.json')
        >>> df.dtypes
        [('age', 'bigint'), ('name', 'string')]

        """
        self._jreader = self._jreader.format(source)
        return self

    def schema(self, schema: Union[StructType, str]) -> "DataFrameReader":
        """Specifies the input schema.

        Some data sources (e.g. JSON) can infer the input schema automatically from data.
        By specifying the schema here, the underlying data source can skip the schema
        inference step, and thus speed up data loading.

        .. versionadded:: 1.4.0

        Parameters
        ----------
        schema : :class:`pyspark.sql.types.StructType` or str
            a :class:`pyspark.sql.types.StructType` object or a DDL-formatted string
            (For example ``col0 INT, col1 DOUBLE``).

        >>> s = spark.read.schema("col0 INT, col1 DOUBLE")
        """
        from pyspark.sql import SparkSession

        spark = SparkSession._getActiveSessionOrCreate()
        if isinstance(schema, StructType):
            jschema = spark._jsparkSession.parseDataType(
                schema.json()
            )  # type: ignore[attr-defined]
            self._jreader = self._jreader.schema(jschema)
        elif isinstance(schema, str):
            self._jreader = self._jreader.schema(schema)
        else:
            raise TypeError("schema should be StructType or string")
        return self

    @since(1.5)
    def option(self, key: str, value: "OptionalPrimitiveType") -> "DataFrameReader":
        """Adds an input option for the underlying data source."""
        self._jreader = self._jreader.option(key, to_str(value))
        return self

    @since(1.4)
    def options(self, **options: "OptionalPrimitiveType") -> "DataFrameReader":
        """Adds input options for the underlying data source."""
        for k in options:
            self._jreader = self._jreader.option(k, to_str(options[k]))
        return self

    def load(
        self,
        path: Optional[PathOrPaths] = None,
        format: Optional[str] = None,
        schema: Optional[Union[StructType, str]] = None,
        **options: "OptionalPrimitiveType",
    ) -> "DataFrame":
        """Loads data from a data source and returns it as a :class:`DataFrame`.

        .. versionadded:: 1.4.0

        Parameters
        ----------
        path : str or list, optional
            optional string or a list of string for file-system backed data sources.
        format : str, optional
            optional string for format of the data source. Default to 'parquet'.
        schema : :class:`pyspark.sql.types.StructType` or str, optional
            optional :class:`pyspark.sql.types.StructType` for the input schema
            or a DDL-formatted string (For example ``col0 INT, col1 DOUBLE``).
        **options : dict
            all other string options

        Examples
        --------
        >>> df = spark.read.format("parquet").load('python/test_support/sql/parquet_partitioned',
        ...     opt1=True, opt2=1, opt3='str')
        >>> df.dtypes
        [('name', 'string'), ('year', 'int'), ('month', 'int'), ('day', 'int')]

        >>> df = spark.read.format('json').load(['python/test_support/sql/people.json',
        ...     'python/test_support/sql/people1.json'])
        >>> df.dtypes
        [('age', 'bigint'), ('aka', 'string'), ('name', 'string')]
        """
        if format is not None:
            self.format(format)
        if schema is not None:
            self.schema(schema)
        self.options(**options)
        if isinstance(path, str):
            return self._df(self._jreader.load(path))
        elif path is not None:
            if type(path) != list:
                path = [path]  # type: ignore[list-item]
            assert self._spark._sc._jvm is not None
            return self._df(self._jreader.load(self._spark._sc._jvm.PythonUtils.toSeq(path)))
        else:
            return self._df(self._jreader.load())

    def json(
        self,
        path: Union[str, List[str], "RDD[str]"],
        schema: Optional[Union[StructType, str]] = None,
        primitivesAsString: Optional[Union[bool, str]] = None,
        prefersDecimal: Optional[Union[bool, str]] = None,
        allowComments: Optional[Union[bool, str]] = None,
        allowUnquotedFieldNames: Optional[Union[bool, str]] = None,
        allowSingleQuotes: Optional[Union[bool, str]] = None,
        allowNumericLeadingZero: Optional[Union[bool, str]] = None,
        allowBackslashEscapingAnyCharacter: Optional[Union[bool, str]] = None,
        mode: Optional[str] = None,
        columnNameOfCorruptRecord: Optional[str] = None,
        dateFormat: Optional[str] = None,
        timestampFormat: Optional[str] = None,
        multiLine: Optional[Union[bool, str]] = None,
        allowUnquotedControlChars: Optional[Union[bool, str]] = None,
        lineSep: Optional[str] = None,
        samplingRatio: Optional[Union[float, str]] = None,
        dropFieldIfAllNull: Optional[Union[bool, str]] = None,
        encoding: Optional[str] = None,
        locale: Optional[str] = None,
        pathGlobFilter: Optional[Union[bool, str]] = None,
        recursiveFileLookup: Optional[Union[bool, str]] = None,
        modifiedBefore: Optional[Union[bool, str]] = None,
        modifiedAfter: Optional[Union[bool, str]] = None,
        allowNonNumericNumbers: Optional[Union[bool, str]] = None,
    ) -> "DataFrame":
        """
        Loads JSON files and returns the results as a :class:`DataFrame`.

        `JSON Lines <http://jsonlines.org/>`_ (newline-delimited JSON) is supported by default.
        For JSON (one record per file), set the ``multiLine`` parameter to ``true``.

        If the ``schema`` parameter is not specified, this function goes
        through the input once to determine the input schema.

        .. versionadded:: 1.4.0

        Parameters
        ----------
        path : str, list or :class:`RDD`
            string represents path to the JSON dataset, or a list of paths,
            or RDD of Strings storing JSON objects.
        schema : :class:`pyspark.sql.types.StructType` or str, optional
            an optional :class:`pyspark.sql.types.StructType` for the input schema or
            a DDL-formatted string (For example ``col0 INT, col1 DOUBLE``).

        Other Parameters
        ----------------
        Extra options
            For the extra options, refer to
            `Data Source Option <https://spark.apache.org/docs/latest/sql-data-sources-json.html#data-source-option>`_
            in the version you use.

            .. # noqa

        Examples
        --------
        >>> df1 = spark.read.json('python/test_support/sql/people.json')
        >>> df1.dtypes
        [('age', 'bigint'), ('name', 'string')]
        >>> rdd = sc.textFile('python/test_support/sql/people.json')
        >>> df2 = spark.read.json(rdd)
        >>> df2.dtypes
        [('age', 'bigint'), ('name', 'string')]

        """
        self._set_opts(
            schema=schema,
            primitivesAsString=primitivesAsString,
            prefersDecimal=prefersDecimal,
            allowComments=allowComments,
            allowUnquotedFieldNames=allowUnquotedFieldNames,
            allowSingleQuotes=allowSingleQuotes,
            allowNumericLeadingZero=allowNumericLeadingZero,
            allowBackslashEscapingAnyCharacter=allowBackslashEscapingAnyCharacter,
            mode=mode,
            columnNameOfCorruptRecord=columnNameOfCorruptRecord,
            dateFormat=dateFormat,
            timestampFormat=timestampFormat,
            multiLine=multiLine,
            allowUnquotedControlChars=allowUnquotedControlChars,
            lineSep=lineSep,
            samplingRatio=samplingRatio,
            dropFieldIfAllNull=dropFieldIfAllNull,
            encoding=encoding,
            locale=locale,
            pathGlobFilter=pathGlobFilter,
            recursiveFileLookup=recursiveFileLookup,
            modifiedBefore=modifiedBefore,
            modifiedAfter=modifiedAfter,
            allowNonNumericNumbers=allowNonNumericNumbers,
        )
        if isinstance(path, str):
            path = [path]
        if type(path) == list:
            assert self._spark._sc._jvm is not None
            return self._df(
                self._jreader.json(
                    self._spark._sc._jvm.PythonUtils.toSeq(path)  # type: ignore[attr-defined]
                )
            )
        elif isinstance(path, RDD):

            def func(iterator: Iterable) -> Iterable:
                for x in iterator:
                    if not isinstance(x, str):
                        x = str(x)
                    if isinstance(x, str):
                        x = x.encode("utf-8")
                    yield x

            keyed = path.mapPartitions(func)
            keyed._bypass_serializer = True  # type: ignore[attr-defined]
            assert self._spark._jvm is not None
            jrdd = keyed._jrdd.map(self._spark._jvm.BytesToString())  # type: ignore[attr-defined]
            return self._df(self._jreader.json(jrdd))
        else:
            raise TypeError("path can be only string, list or RDD")

    def table(self, tableName: str) -> "DataFrame":
        """Returns the specified table as a :class:`DataFrame`.

        .. versionadded:: 1.4.0

        Parameters
        ----------
        tableName : str
            string, name of the table.

        Examples
        --------
        >>> df = spark.read.parquet('python/test_support/sql/parquet_partitioned')
        >>> df.createOrReplaceTempView('tmpTable')
        >>> spark.read.table('tmpTable').dtypes
        [('name', 'string'), ('year', 'int'), ('month', 'int'), ('day', 'int')]
        """
        return self._df(self._jreader.table(tableName))

    def parquet(self, *paths: str, **options: "OptionalPrimitiveType") -> "DataFrame":
        """
        Loads Parquet files, returning the result as a :class:`DataFrame`.

        .. versionadded:: 1.4.0

        Parameters
        ----------
        paths : str

        Other Parameters
        ----------------
        **options
            For the extra options, refer to
            `Data Source Option <https://spark.apache.org/docs/latest/sql-data-sources-parquet.html#data-source-option>`_
            in the version you use.

            .. # noqa

        Examples
        --------
        >>> df = spark.read.parquet('python/test_support/sql/parquet_partitioned')
        >>> df.dtypes
        [('name', 'string'), ('year', 'int'), ('month', 'int'), ('day', 'int')]
        """
        mergeSchema = options.get("mergeSchema", None)
        pathGlobFilter = options.get("pathGlobFilter", None)
        modifiedBefore = options.get("modifiedBefore", None)
        modifiedAfter = options.get("modifiedAfter", None)
        recursiveFileLookup = options.get("recursiveFileLookup", None)
        datetimeRebaseMode = options.get("datetimeRebaseMode", None)
        int96RebaseMode = options.get("int96RebaseMode", None)
        self._set_opts(
            mergeSchema=mergeSchema,
            pathGlobFilter=pathGlobFilter,
            recursiveFileLookup=recursiveFileLookup,
            modifiedBefore=modifiedBefore,
            modifiedAfter=modifiedAfter,
            datetimeRebaseMode=datetimeRebaseMode,
            int96RebaseMode=int96RebaseMode,
        )

        return self._df(self._jreader.parquet(_to_seq(self._spark._sc, paths)))

    def text(
        self,
        paths: PathOrPaths,
        wholetext: bool = False,
        lineSep: Optional[str] = None,
        pathGlobFilter: Optional[Union[bool, str]] = None,
        recursiveFileLookup: Optional[Union[bool, str]] = None,
        modifiedBefore: Optional[Union[bool, str]] = None,
        modifiedAfter: Optional[Union[bool, str]] = None,
    ) -> "DataFrame":
        """
        Loads text files and returns a :class:`DataFrame` whose schema starts with a
        string column named "value", and followed by partitioned columns if there
        are any.
        The text files must be encoded as UTF-8.

        By default, each line in the text file is a new row in the resulting DataFrame.

        .. versionadded:: 1.6.0

        Parameters
        ----------
        paths : str or list
            string, or list of strings, for input path(s).

        Other Parameters
        ----------------
        Extra options
            For the extra options, refer to
            `Data Source Option <https://spark.apache.org/docs/latest/sql-data-sources-text.html#data-source-option>`_
            in the version you use.

            .. # noqa

        Examples
        --------
        >>> df = spark.read.text('python/test_support/sql/text-test.txt')
        >>> df.collect()
        [Row(value='hello'), Row(value='this')]
        >>> df = spark.read.text('python/test_support/sql/text-test.txt', wholetext=True)
        >>> df.collect()
        [Row(value='hello\\nthis')]
        """
        self._set_opts(
            wholetext=wholetext,
            lineSep=lineSep,
            pathGlobFilter=pathGlobFilter,
            recursiveFileLookup=recursiveFileLookup,
            modifiedBefore=modifiedBefore,
            modifiedAfter=modifiedAfter,
        )

        if isinstance(paths, str):
            paths = [paths]
        assert self._spark._sc._jvm is not None
        return self._df(
            self._jreader.text(
                self._spark._sc._jvm.PythonUtils.toSeq(paths)  # type: ignore[attr-defined]
            )
        )

    def csv(
        self,
        path: PathOrPaths,
        schema: Optional[Union[StructType, str]] = None,
        sep: Optional[str] = None,
        encoding: Optional[str] = None,
        quote: Optional[str] = None,
        escape: Optional[str] = None,
        comment: Optional[str] = None,
        header: Optional[Union[bool, str]] = None,
        inferSchema: Optional[Union[bool, str]] = None,
        ignoreLeadingWhiteSpace: Optional[Union[bool, str]] = None,
        ignoreTrailingWhiteSpace: Optional[Union[bool, str]] = None,
        nullValue: Optional[str] = None,
        nanValue: Optional[str] = None,
        positiveInf: Optional[str] = None,
        negativeInf: Optional[str] = None,
        dateFormat: Optional[str] = None,
        timestampFormat: Optional[str] = None,
        maxColumns: Optional[Union[int, str]] = None,
        maxCharsPerColumn: Optional[Union[int, str]] = None,
        maxMalformedLogPerPartition: Optional[Union[int, str]] = None,
        mode: Optional[str] = None,
        columnNameOfCorruptRecord: Optional[str] = None,
        multiLine: Optional[Union[bool, str]] = None,
        charToEscapeQuoteEscaping: Optional[str] = None,
        samplingRatio: Optional[Union[float, str]] = None,
        enforceSchema: Optional[Union[bool, str]] = None,
        emptyValue: Optional[str] = None,
        locale: Optional[str] = None,
        lineSep: Optional[str] = None,
        pathGlobFilter: Optional[Union[bool, str]] = None,
        recursiveFileLookup: Optional[Union[bool, str]] = None,
        modifiedBefore: Optional[Union[bool, str]] = None,
        modifiedAfter: Optional[Union[bool, str]] = None,
        unescapedQuoteHandling: Optional[str] = None,
    ) -> "DataFrame":
        r"""Loads a CSV file and returns the result as a  :class:`DataFrame`.

        This function will go through the input once to determine the input schema if
        ``inferSchema`` is enabled. To avoid going through the entire data once, disable
        ``inferSchema`` option or specify the schema explicitly using ``schema``.

        .. versionadded:: 2.0.0

        Parameters
        ----------
        path : str or list
            string, or list of strings, for input path(s),
            or RDD of Strings storing CSV rows.
        schema : :class:`pyspark.sql.types.StructType` or str, optional
            an optional :class:`pyspark.sql.types.StructType` for the input schema
            or a DDL-formatted string (For example ``col0 INT, col1 DOUBLE``).

        Other Parameters
        ----------------
        Extra options
            For the extra options, refer to
            `Data Source Option <https://spark.apache.org/docs/latest/sql-data-sources-csv.html#data-source-option>`_
            in the version you use.

            .. # noqa

        Examples
        --------
        >>> df = spark.read.csv('python/test_support/sql/ages.csv')
        >>> df.dtypes
        [('_c0', 'string'), ('_c1', 'string')]
        >>> rdd = sc.textFile('python/test_support/sql/ages.csv')
        >>> df2 = spark.read.csv(rdd)
        >>> df2.dtypes
        [('_c0', 'string'), ('_c1', 'string')]
        """
        self._set_opts(
            schema=schema,
            sep=sep,
            encoding=encoding,
            quote=quote,
            escape=escape,
            comment=comment,
            header=header,
            inferSchema=inferSchema,
            ignoreLeadingWhiteSpace=ignoreLeadingWhiteSpace,
            ignoreTrailingWhiteSpace=ignoreTrailingWhiteSpace,
            nullValue=nullValue,
            nanValue=nanValue,
            positiveInf=positiveInf,
            negativeInf=negativeInf,
            dateFormat=dateFormat,
            timestampFormat=timestampFormat,
            maxColumns=maxColumns,
            maxCharsPerColumn=maxCharsPerColumn,
            maxMalformedLogPerPartition=maxMalformedLogPerPartition,
            mode=mode,
            columnNameOfCorruptRecord=columnNameOfCorruptRecord,
            multiLine=multiLine,
            charToEscapeQuoteEscaping=charToEscapeQuoteEscaping,
            samplingRatio=samplingRatio,
            enforceSchema=enforceSchema,
            emptyValue=emptyValue,
            locale=locale,
            lineSep=lineSep,
            pathGlobFilter=pathGlobFilter,
            recursiveFileLookup=recursiveFileLookup,
            modifiedBefore=modifiedBefore,
            modifiedAfter=modifiedAfter,
            unescapedQuoteHandling=unescapedQuoteHandling,
        )
        if isinstance(path, str):
            path = [path]
        if type(path) == list:
            assert self._spark._sc._jvm is not None
            return self._df(self._jreader.csv(self._spark._sc._jvm.PythonUtils.toSeq(path)))
        elif isinstance(path, RDD):

            def func(iterator):
                for x in iterator:
                    if not isinstance(x, str):
                        x = str(x)
                    if isinstance(x, str):
                        x = x.encode("utf-8")
                    yield x

            keyed = path.mapPartitions(func)
            keyed._bypass_serializer = True
            jrdd = keyed._jrdd.map(self._spark._jvm.BytesToString())
            # see SPARK-22112
            # There aren't any jvm api for creating a dataframe from rdd storing csv.
            # We can do it through creating a jvm dataset firstly and using the jvm api
            # for creating a dataframe from dataset storing csv.
            jdataset = self._spark._jsparkSession.createDataset(
                jrdd.rdd(), self._spark._jvm.Encoders.STRING()
            )
            return self._df(self._jreader.csv(jdataset))
        else:
            raise TypeError("path can be only string, list or RDD")

    def orc(
        self,
        path: PathOrPaths,
        mergeSchema: Optional[bool] = None,
        pathGlobFilter: Optional[Union[bool, str]] = None,
        recursiveFileLookup: Optional[Union[bool, str]] = None,
        modifiedBefore: Optional[Union[bool, str]] = None,
        modifiedAfter: Optional[Union[bool, str]] = None,
    ) -> "DataFrame":
        """Loads ORC files, returning the result as a :class:`DataFrame`.

        .. versionadded:: 1.5.0

        Parameters
        ----------
        path : str or list

        Other Parameters
        ----------------
        Extra options
            For the extra options, refer to
            `Data Source Option <https://spark.apache.org/docs/latest/sql-data-sources-orc.html#data-source-option>`_
            in the version you use.

            .. # noqa

        Examples
        --------
        >>> df = spark.read.orc('python/test_support/sql/orc_partitioned')
        >>> df.dtypes
        [('a', 'bigint'), ('b', 'int'), ('c', 'int')]
        """
        self._set_opts(
            mergeSchema=mergeSchema,
            pathGlobFilter=pathGlobFilter,
            modifiedBefore=modifiedBefore,
            modifiedAfter=modifiedAfter,
            recursiveFileLookup=recursiveFileLookup,
        )
        if isinstance(path, str):
            path = [path]
        return self._df(self._jreader.orc(_to_seq(self._spark._sc, path)))

    @overload
    def jdbc(
        self, url: str, table: str, *, properties: Optional[Dict[str, str]] = None
    ) -> "DataFrame":
        ...

    @overload
    def jdbc(
        self,
        url: str,
        table: str,
        column: str,
        lowerBound: Union[int, str],
        upperBound: Union[int, str],
        numPartitions: int,
        *,
        properties: Optional[Dict[str, str]] = None,
    ) -> "DataFrame":
        ...

    @overload
    def jdbc(
        self,
        url: str,
        table: str,
        *,
        predicates: List[str],
        properties: Optional[Dict[str, str]] = None,
    ) -> "DataFrame":
        ...

    def jdbc(
        self,
        url: str,
        table: str,
        column: Optional[str] = None,
        lowerBound: Optional[Union[int, str]] = None,
        upperBound: Optional[Union[int, str]] = None,
        numPartitions: Optional[int] = None,
        predicates: Optional[List[str]] = None,
        properties: Optional[Dict[str, str]] = None,
    ) -> "DataFrame":
        """
        Construct a :class:`DataFrame` representing the database table named ``table``
        accessible via JDBC URL ``url`` and connection ``properties``.

        Partitions of the table will be retrieved in parallel if either ``column`` or
        ``predicates`` is specified. ``lowerBound``, ``upperBound`` and ``numPartitions``
        is needed when ``column`` is specified.

        If both ``column`` and ``predicates`` are specified, ``column`` will be used.

        .. versionadded:: 1.4.0

        Parameters
        ----------
        table : str
            the name of the table
        column : str, optional
            alias of ``partitionColumn`` option. Refer to ``partitionColumn`` in
            `Data Source Option <https://spark.apache.org/docs/latest/sql-data-sources-jdbc.html#data-source-option>`_
            in the version you use.
        predicates : list, optional
            a list of expressions suitable for inclusion in WHERE clauses;
            each one defines one partition of the :class:`DataFrame`
        properties : dict, optional
            a dictionary of JDBC database connection arguments. Normally at
            least properties "user" and "password" with their corresponding values.
            For example { 'user' : 'SYSTEM', 'password' : 'mypassword' }

        Other Parameters
        ----------------
        Extra options
            For the extra options, refer to
            `Data Source Option <https://spark.apache.org/docs/latest/sql-data-sources-jdbc.html#data-source-option>`_
            in the version you use.

            .. # noqa

        Notes
        -----
        Don't create too many partitions in parallel on a large cluster;
        otherwise Spark might crash your external database systems.

        Returns
        -------
        :class:`DataFrame`
        """
        if properties is None:
            properties = dict()
        assert self._spark._sc._gateway is not None
        jprop = JavaClass(
            "java.util.Properties",
            self._spark._sc._gateway._gateway_client,
        )()
        for k in properties:
            jprop.setProperty(k, properties[k])
        if column is not None:
            assert lowerBound is not None, "lowerBound can not be None when ``column`` is specified"
            assert upperBound is not None, "upperBound can not be None when ``column`` is specified"
            assert (
                numPartitions is not None
            ), "numPartitions can not be None when ``column`` is specified"
            return self._df(
                self._jreader.jdbc(
                    url, table, column, int(lowerBound), int(upperBound), int(numPartitions), jprop
                )
            )
        if predicates is not None:
            gateway = self._spark._sc._gateway
            assert gateway is not None
            jpredicates = utils.toJArray(gateway, gateway.jvm.java.lang.String, predicates)
            return self._df(self._jreader.jdbc(url, table, jpredicates, jprop))
        return self._df(self._jreader.jdbc(url, table, jprop))


class DataFrameWriter(OptionUtils):
    """
    Interface used to write a :class:`DataFrame` to external storage systems
    (e.g. file systems, key-value stores, etc). Use :attr:`DataFrame.write`
    to access this.

    .. versionadded:: 1.4
    """

    def __init__(self, df: "DataFrame"):
        self._df = df
        self._spark = df.sparkSession
        self._jwrite = df._jdf.write()  # type: ignore[operator]

    def _sq(self, jsq: JavaObject) -> "StreamingQuery":
        from pyspark.sql.streaming import StreamingQuery

        return StreamingQuery(jsq)

    def mode(self, saveMode: Optional[str]) -> "DataFrameWriter":
        """Specifies the behavior when data or table already exists.

        Options include:

        * `append`: Append contents of this :class:`DataFrame` to existing data.
        * `overwrite`: Overwrite existing data.
        * `error` or `errorifexists`: Throw an exception if data already exists.
        * `ignore`: Silently ignore this operation if data already exists.

        .. versionadded:: 1.4.0

        Examples
        --------
        >>> df.write.mode('append').parquet(os.path.join(tempfile.mkdtemp(), 'data'))
        """
        # At the JVM side, the default value of mode is already set to "error".
        # So, if the given saveMode is None, we will not call JVM-side's mode method.
        if saveMode is not None:
            self._jwrite = self._jwrite.mode(saveMode)
        return self

    def format(self, source: str) -> "DataFrameWriter":
        """Specifies the underlying output data source.

        .. versionadded:: 1.4.0

        Parameters
        ----------
        source : str
            string, name of the data source, e.g. 'json', 'parquet'.

        Examples
        --------
        >>> df.write.format('json').save(os.path.join(tempfile.mkdtemp(), 'data'))
        """
        self._jwrite = self._jwrite.format(source)
        return self

    @since(1.5)
    def option(self, key: str, value: "OptionalPrimitiveType") -> "DataFrameWriter":
        """Adds an output option for the underlying data source."""
        self._jwrite = self._jwrite.option(key, to_str(value))
        return self

    @since(1.4)
    def options(self, **options: "OptionalPrimitiveType") -> "DataFrameWriter":
        """Adds output options for the underlying data source."""
        for k in options:
            self._jwrite = self._jwrite.option(k, to_str(options[k]))
        return self

    @overload
    def partitionBy(self, *cols: str) -> "DataFrameWriter":
        ...

    @overload
    def partitionBy(self, *cols: List[str]) -> "DataFrameWriter":
        ...

    def partitionBy(self, *cols: Union[str, List[str]]) -> "DataFrameWriter":
        """Partitions the output by the given columns on the file system.

        If specified, the output is laid out on the file system similar
        to Hive's partitioning scheme.

        .. versionadded:: 1.4.0

        Parameters
        ----------
        cols : str or list
            name of columns

        Examples
        --------
        >>> df.write.partitionBy('year', 'month').parquet(os.path.join(tempfile.mkdtemp(), 'data'))
        """
        if len(cols) == 1 and isinstance(cols[0], (list, tuple)):
            cols = cols[0]  # type: ignore[assignment]
        self._jwrite = self._jwrite.partitionBy(
            _to_seq(self._spark._sc, cast(Iterable["ColumnOrName"], cols))
        )
        return self

    @overload
    def bucketBy(self, numBuckets: int, col: str, *cols: str) -> "DataFrameWriter":
        ...

    @overload
    def bucketBy(self, numBuckets: int, col: TupleOrListOfString) -> "DataFrameWriter":
        ...

    def bucketBy(
        self, numBuckets: int, col: Union[str, TupleOrListOfString], *cols: Optional[str]
    ) -> "DataFrameWriter":
        """Buckets the output by the given columns. If specified,
        the output is laid out on the file system similar to Hive's bucketing scheme,
        but with a different bucket hash function and is not compatible with Hive's bucketing.

        .. versionadded:: 2.3.0

        Parameters
        ----------
        numBuckets : int
            the number of buckets to save
        col : str, list or tuple
            a name of a column, or a list of names.
        cols : str
            additional names (optional). If `col` is a list it should be empty.

        Notes
        -----
        Applicable for file-based data sources in combination with
        :py:meth:`DataFrameWriter.saveAsTable`.

        Examples
        --------
        >>> (df.write.format('parquet')  # doctest: +SKIP
        ...     .bucketBy(100, 'year', 'month')
        ...     .mode("overwrite")
        ...     .saveAsTable('bucketed_table'))
        """
        if not isinstance(numBuckets, int):
            raise TypeError("numBuckets should be an int, got {0}.".format(type(numBuckets)))

        if isinstance(col, (list, tuple)):
            if cols:
                raise ValueError("col is a {0} but cols are not empty".format(type(col)))

            col, cols = col[0], col[1:]  # type: ignore[assignment]

        if not all(isinstance(c, str) for c in cols) or not (isinstance(col, str)):
            raise TypeError("all names should be `str`")

        self._jwrite = self._jwrite.bucketBy(
            numBuckets, col, _to_seq(self._spark._sc, cast(Iterable["ColumnOrName"], cols))
        )
        return self

    @overload
    def sortBy(self, col: str, *cols: str) -> "DataFrameWriter":
        ...

    @overload
    def sortBy(self, col: TupleOrListOfString) -> "DataFrameWriter":
        ...

    def sortBy(
        self, col: Union[str, TupleOrListOfString], *cols: Optional[str]
    ) -> "DataFrameWriter":
        """Sorts the output in each bucket by the given columns on the file system.

        .. versionadded:: 2.3.0

        Parameters
        ----------
        col : str, tuple or list
            a name of a column, or a list of names.
        cols : str
            additional names (optional). If `col` is a list it should be empty.

        Examples
        --------
        >>> (df.write.format('parquet')  # doctest: +SKIP
        ...     .bucketBy(100, 'year', 'month')
        ...     .sortBy('day')
        ...     .mode("overwrite")
        ...     .saveAsTable('sorted_bucketed_table'))
        """
        if isinstance(col, (list, tuple)):
            if cols:
                raise ValueError("col is a {0} but cols are not empty".format(type(col)))

            col, cols = col[0], col[1:]  # type: ignore[assignment]

        if not all(isinstance(c, str) for c in cols) or not (isinstance(col, str)):
            raise TypeError("all names should be `str`")

        self._jwrite = self._jwrite.sortBy(
            col, _to_seq(self._spark._sc, cast(Iterable["ColumnOrName"], cols))
        )
        return self

    def save(
        self,
        path: Optional[str] = None,
        format: Optional[str] = None,
        mode: Optional[str] = None,
        partitionBy: Optional[Union[str, List[str]]] = None,
        **options: "OptionalPrimitiveType",
    ) -> None:
        """Saves the contents of the :class:`DataFrame` to a data source.

        The data source is specified by the ``format`` and a set of ``options``.
        If ``format`` is not specified, the default data source configured by
        ``spark.sql.sources.default`` will be used.

        .. versionadded:: 1.4.0

        Parameters
        ----------
        path : str, optional
            the path in a Hadoop supported file system
        format : str, optional
            the format used to save
        mode : str, optional
            specifies the behavior of the save operation when data already exists.

            * ``append``: Append contents of this :class:`DataFrame` to existing data.
            * ``overwrite``: Overwrite existing data.
            * ``ignore``: Silently ignore this operation if data already exists.
            * ``error`` or ``errorifexists`` (default case): Throw an exception if data already \
                exists.
        partitionBy : list, optional
            names of partitioning columns
        **options : dict
            all other string options

        Examples
        --------
        >>> df.write.mode("append").save(os.path.join(tempfile.mkdtemp(), 'data'))
        """
        self.mode(mode).options(**options)
        if partitionBy is not None:
            self.partitionBy(partitionBy)
        if format is not None:
            self.format(format)
        if path is None:
            self._jwrite.save()
        else:
            self._jwrite.save(path)

    @since(1.4)
    def insertInto(self, tableName: str, overwrite: Optional[bool] = None) -> None:
        """Inserts the content of the :class:`DataFrame` to the specified table.

        It requires that the schema of the :class:`DataFrame` is the same as the
        schema of the table.

        Parameters
        ----------
        overwrite : bool, optional
            If true, overwrites existing data. Disabled by default

        Notes
        -----
        Unlike :meth:`DataFrameWriter.saveAsTable`, :meth:`DataFrameWriter.insertInto` ignores
        the column names and just uses position-based resolution.

        """
        if overwrite is not None:
            self.mode("overwrite" if overwrite else "append")
        self._jwrite.insertInto(tableName)

    def saveAsTable(
        self,
        name: str,
        format: Optional[str] = None,
        mode: Optional[str] = None,
        partitionBy: Optional[Union[str, List[str]]] = None,
        **options: "OptionalPrimitiveType",
    ) -> None:
        """Saves the content of the :class:`DataFrame` as the specified table.

        In the case the table already exists, behavior of this function depends on the
        save mode, specified by the `mode` function (default to throwing an exception).
        When `mode` is `Overwrite`, the schema of the :class:`DataFrame` does not need to be
        the same as that of the existing table.

        * `append`: Append contents of this :class:`DataFrame` to existing data.
        * `overwrite`: Overwrite existing data.
        * `error` or `errorifexists`: Throw an exception if data already exists.
        * `ignore`: Silently ignore this operation if data already exists.

        .. versionadded:: 1.4.0

        Notes
        -----
        When `mode` is `Append`, if there is an existing table, we will use the format and
        options of the existing table. The column order in the schema of the :class:`DataFrame`
        doesn't need to be same as that of the existing table. Unlike
        :meth:`DataFrameWriter.insertInto`, :meth:`DataFrameWriter.saveAsTable` will use the
        column names to find the correct column positions.

        Parameters
        ----------
        name : str
            the table name
        format : str, optional
            the format used to save
        mode : str, optional
            one of `append`, `overwrite`, `error`, `errorifexists`, `ignore` \
            (default: error)
        partitionBy : str or list
            names of partitioning columns
        **options : dict
            all other string options
        """
        self.mode(mode).options(**options)
        if partitionBy is not None:
            self.partitionBy(partitionBy)
        if format is not None:
            self.format(format)
        self._jwrite.saveAsTable(name)

    def json(
        self,
        path: str,
        mode: Optional[str] = None,
        compression: Optional[str] = None,
        dateFormat: Optional[str] = None,
        timestampFormat: Optional[str] = None,
        lineSep: Optional[str] = None,
        encoding: Optional[str] = None,
        ignoreNullFields: Optional[Union[bool, str]] = None,
    ) -> None:
        """Saves the content of the :class:`DataFrame` in JSON format
        (`JSON Lines text format or newline-delimited JSON <http://jsonlines.org/>`_) at the
        specified path.

        .. versionadded:: 1.4.0

        Parameters
        ----------
        path : str
            the path in any Hadoop supported file system
        mode : str, optional
            specifies the behavior of the save operation when data already exists.

            * ``append``: Append contents of this :class:`DataFrame` to existing data.
            * ``overwrite``: Overwrite existing data.
            * ``ignore``: Silently ignore this operation if data already exists.
            * ``error`` or ``errorifexists`` (default case): Throw an exception if data already \
                exists.

        Other Parameters
        ----------------
        Extra options
            For the extra options, refer to
            `Data Source Option <https://spark.apache.org/docs/latest/sql-data-sources-json.html#data-source-option>`_
            in the version you use.

            .. # noqa

        Examples
        --------
        >>> df.write.json(os.path.join(tempfile.mkdtemp(), 'data'))
        """
        self.mode(mode)
        self._set_opts(
            compression=compression,
            dateFormat=dateFormat,
            timestampFormat=timestampFormat,
            lineSep=lineSep,
            encoding=encoding,
            ignoreNullFields=ignoreNullFields,
        )
        self._jwrite.json(path)

    def parquet(
        self,
        path: str,
        mode: Optional[str] = None,
        partitionBy: Optional[Union[str, List[str]]] = None,
        compression: Optional[str] = None,
    ) -> None:
        """Saves the content of the :class:`DataFrame` in Parquet format at the specified path.

        .. versionadded:: 1.4.0

        Parameters
        ----------
        path : str
            the path in any Hadoop supported file system
        mode : str, optional
            specifies the behavior of the save operation when data already exists.

            * ``append``: Append contents of this :class:`DataFrame` to existing data.
            * ``overwrite``: Overwrite existing data.
            * ``ignore``: Silently ignore this operation if data already exists.
            * ``error`` or ``errorifexists`` (default case): Throw an exception if data already \
                exists.
        partitionBy : str or list, optional
            names of partitioning columns

        Other Parameters
        ----------------
        Extra options
            For the extra options, refer to
            `Data Source Option <https://spark.apache.org/docs/latest/sql-data-sources-parquet.html#data-source-option>`_
            in the version you use.

            .. # noqa

        Examples
        --------
        >>> df.write.parquet(os.path.join(tempfile.mkdtemp(), 'data'))
        """
        self.mode(mode)
        if partitionBy is not None:
            self.partitionBy(partitionBy)
        self._set_opts(compression=compression)
        self._jwrite.parquet(path)

    def text(
        self, path: str, compression: Optional[str] = None, lineSep: Optional[str] = None
    ) -> None:
        """Saves the content of the DataFrame in a text file at the specified path.
        The text files will be encoded as UTF-8.

        .. versionadded:: 1.6.0

        Parameters
        ----------
        path : str
            the path in any Hadoop supported file system

        Other Parameters
        ----------------
        Extra options
            For the extra options, refer to
            `Data Source Option <https://spark.apache.org/docs/latest/sql-data-sources-text.html#data-source-option>`_
            in the version you use.

            .. # noqa

        The DataFrame must have only one column that is of string type.
        Each row becomes a new line in the output file.
        """
        self._set_opts(compression=compression, lineSep=lineSep)
        self._jwrite.text(path)

    def csv(
        self,
        path: str,
        mode: Optional[str] = None,
        compression: Optional[str] = None,
        sep: Optional[str] = None,
        quote: Optional[str] = None,
        escape: Optional[str] = None,
        header: Optional[Union[bool, str]] = None,
        nullValue: Optional[str] = None,
        escapeQuotes: Optional[Union[bool, str]] = None,
        quoteAll: Optional[Union[bool, str]] = None,
        dateFormat: Optional[str] = None,
        timestampFormat: Optional[str] = None,
        ignoreLeadingWhiteSpace: Optional[Union[bool, str]] = None,
        ignoreTrailingWhiteSpace: Optional[Union[bool, str]] = None,
        charToEscapeQuoteEscaping: Optional[str] = None,
        encoding: Optional[str] = None,
        emptyValue: Optional[str] = None,
        lineSep: Optional[str] = None,
    ) -> None:
        r"""Saves the content of the :class:`DataFrame` in CSV format at the specified path.

        .. versionadded:: 2.0.0

        Parameters
        ----------
        path : str
            the path in any Hadoop supported file system
        mode : str, optional
            specifies the behavior of the save operation when data already exists.

            * ``append``: Append contents of this :class:`DataFrame` to existing data.
            * ``overwrite``: Overwrite existing data.
            * ``ignore``: Silently ignore this operation if data already exists.
            * ``error`` or ``errorifexists`` (default case): Throw an exception if data already \
                exists.

        Other Parameters
        ----------------
        Extra options
            For the extra options, refer to
            `Data Source Option <https://spark.apache.org/docs/latest/sql-data-sources-csv.html#data-source-option>`_
            in the version you use.

            .. # noqa

        Examples
        --------
        >>> df.write.csv(os.path.join(tempfile.mkdtemp(), 'data'))
        """
        self.mode(mode)
        self._set_opts(
            compression=compression,
            sep=sep,
            quote=quote,
            escape=escape,
            header=header,
            nullValue=nullValue,
            escapeQuotes=escapeQuotes,
            quoteAll=quoteAll,
            dateFormat=dateFormat,
            timestampFormat=timestampFormat,
            ignoreLeadingWhiteSpace=ignoreLeadingWhiteSpace,
            ignoreTrailingWhiteSpace=ignoreTrailingWhiteSpace,
            charToEscapeQuoteEscaping=charToEscapeQuoteEscaping,
            encoding=encoding,
            emptyValue=emptyValue,
            lineSep=lineSep,
        )
        self._jwrite.csv(path)

    def orc(
        self,
        path: str,
        mode: Optional[str] = None,
        partitionBy: Optional[Union[str, List[str]]] = None,
        compression: Optional[str] = None,
    ) -> None:
        """Saves the content of the :class:`DataFrame` in ORC format at the specified path.

        .. versionadded:: 1.5.0

        Parameters
        ----------
        path : str
            the path in any Hadoop supported file system
        mode : str, optional
            specifies the behavior of the save operation when data already exists.

            * ``append``: Append contents of this :class:`DataFrame` to existing data.
            * ``overwrite``: Overwrite existing data.
            * ``ignore``: Silently ignore this operation if data already exists.
            * ``error`` or ``errorifexists`` (default case): Throw an exception if data already \
                exists.
        partitionBy : str or list, optional
            names of partitioning columns

        Other Parameters
        ----------------
        Extra options
            For the extra options, refer to
            `Data Source Option <https://spark.apache.org/docs/latest/sql-data-sources-orc.html#data-source-option>`_
            in the version you use.

            .. # noqa

        Examples
        --------
        >>> orc_df = spark.read.orc('python/test_support/sql/orc_partitioned')
        >>> orc_df.write.orc(os.path.join(tempfile.mkdtemp(), 'data'))
        """
        self.mode(mode)
        if partitionBy is not None:
            self.partitionBy(partitionBy)
        self._set_opts(compression=compression)
        self._jwrite.orc(path)

    def jdbc(
        self,
        url: str,
        table: str,
        mode: Optional[str] = None,
        properties: Optional[Dict[str, str]] = None,
    ) -> None:
        """Saves the content of the :class:`DataFrame` to an external database table via JDBC.

        .. versionadded:: 1.4.0

        Parameters
        ----------
        table : str
            Name of the table in the external database.
        mode : str, optional
            specifies the behavior of the save operation when data already exists.

            * ``append``: Append contents of this :class:`DataFrame` to existing data.
            * ``overwrite``: Overwrite existing data.
            * ``ignore``: Silently ignore this operation if data already exists.
            * ``error`` or ``errorifexists`` (default case): Throw an exception if data already \
                exists.
        properties : dict
            a dictionary of JDBC database connection arguments. Normally at
            least properties "user" and "password" with their corresponding values.
            For example { 'user' : 'SYSTEM', 'password' : 'mypassword' }

        Other Parameters
        ----------------
        Extra options
            For the extra options, refer to
            `Data Source Option <https://spark.apache.org/docs/latest/sql-data-sources-jdbc.html#data-source-option>`_
            in the version you use.

            .. # noqa

        Notes
        -----
        Don't create too many partitions in parallel on a large cluster;
        otherwise Spark might crash your external database systems.
        """
        if properties is None:
            properties = dict()

        assert self._spark._sc._gateway is not None
        jprop = JavaClass(
            "java.util.Properties",
            self._spark._sc._gateway._gateway_client,
        )()
        for k in properties:
            jprop.setProperty(k, properties[k])
        self.mode(mode)._jwrite.jdbc(url, table, jprop)


class DataFrameWriterV2:
    """
    Interface used to write a class:`pyspark.sql.dataframe.DataFrame`
    to external storage using the v2 API.

    .. versionadded:: 3.1.0
    """

    def __init__(self, df: "DataFrame", table: str):
        self._df = df
        self._spark = df.sparkSession
        self._jwriter = df._jdf.writeTo(table)  # type: ignore[operator]

    @since(3.1)
    def using(self, provider: str) -> "DataFrameWriterV2":
        """
        Specifies a provider for the underlying output data source.
        Spark's default catalog supports "parquet", "json", etc.
        """
        self._jwriter.using(provider)
        return self

    @since(3.1)
    def option(self, key: str, value: "OptionalPrimitiveType") -> "DataFrameWriterV2":
        """
        Add a write option.
        """
        self._jwriter.option(key, to_str(value))
        return self

    @since(3.1)
    def options(self, **options: "OptionalPrimitiveType") -> "DataFrameWriterV2":
        """
        Add write options.
        """
        options = {k: to_str(v) for k, v in options.items()}
        self._jwriter.options(options)
        return self

    @since(3.1)
    def tableProperty(self, property: str, value: str) -> "DataFrameWriterV2":
        """
        Add table property.
        """
        self._jwriter.tableProperty(property, value)
        return self

    @since(3.1)
    def partitionedBy(self, col: Column, *cols: Column) -> "DataFrameWriterV2":
        """
        Partition the output table created by `create`, `createOrReplace`, or `replace` using
        the given columns or transforms.

        When specified, the table data will be stored by these values for efficient reads.

        For example, when a table is partitioned by day, it may be stored
        in a directory layout like:

        * `table/day=2019-06-01/`
        * `table/day=2019-06-02/`

        Partitioning is one of the most widely used techniques to optimize physical data layout.
        It provides a coarse-grained index for skipping unnecessary data reads when queries have
        predicates on the partitioned columns. In order for partitioning to work well, the number
        of distinct values in each column should typically be less than tens of thousands.

        `col` and `cols` support only the following functions:

        * :py:func:`pyspark.sql.functions.years`
        * :py:func:`pyspark.sql.functions.months`
        * :py:func:`pyspark.sql.functions.days`
        * :py:func:`pyspark.sql.functions.hours`
        * :py:func:`pyspark.sql.functions.bucket`

        """
        col = _to_java_column(col)
        cols = _to_seq(self._spark._sc, [_to_java_column(c) for c in cols])
        self._jwriter.partitionedBy(col, cols)
        return self

    @since(3.1)
    def create(self) -> None:
        """
        Create a new table from the contents of the data frame.

        The new table's schema, partition layout, properties, and other configuration will be
        based on the configuration set on this writer.
        """
        self._jwriter.create()

    @since(3.1)
    def replace(self) -> None:
        """
        Replace an existing table with the contents of the data frame.

        The existing table's schema, partition layout, properties, and other configuration will be
        replaced with the contents of the data frame and the configuration set on this writer.
        """
        self._jwriter.replace()

    @since(3.1)
    def createOrReplace(self) -> None:
        """
        Create a new table or replace an existing table with the contents of the data frame.

        The output table's schema, partition layout, properties,
        and other configuration will be based on the contents of the data frame
        and the configuration set on this writer.
        If the table exists, its configuration and data will be replaced.
        """
        self._jwriter.createOrReplace()

    @since(3.1)
    def append(self) -> None:
        """
        Append the contents of the data frame to the output table.
        """
        self._jwriter.append()

    @since(3.1)
    def overwrite(self, condition: Column) -> None:
        """
        Overwrite rows matching the given filter condition with the contents of the data frame in
        the output table.
        """
        self._jwriter.overwrite(condition)

    @since(3.1)
    def overwritePartitions(self) -> None:
        """
        Overwrite all partition for which the data frame contains at least one row with the contents
        of the data frame in the output table.

        This operation is equivalent to Hive's `INSERT OVERWRITE ... PARTITION`, which replaces
        partitions dynamically depending on the contents of the data frame.
        """
        self._jwriter.overwritePartitions()


def _test() -> None:
    import doctest
    import os
    import tempfile
    import py4j
    from pyspark.context import SparkContext
    from pyspark.sql import SparkSession
    import pyspark.sql.readwriter

    os.chdir(os.environ["SPARK_HOME"])

    globs = pyspark.sql.readwriter.__dict__.copy()
    sc = SparkContext("local[4]", "PythonTest")
    try:
        spark = SparkSession._getActiveSessionOrCreate()
    except py4j.protocol.Py4JError:
        spark = SparkSession(sc)

    globs["tempfile"] = tempfile
    globs["os"] = os
    globs["sc"] = sc
    globs["spark"] = spark
    globs["df"] = spark.read.parquet("python/test_support/sql/parquet_partitioned")
    (failure_count, test_count) = doctest.testmod(
        pyspark.sql.readwriter,
        globs=globs,
        optionflags=doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE | doctest.REPORT_NDIFF,
    )
    sc.stop()
    if failure_count:
        sys.exit(-1)


if __name__ == "__main__":
    _test()
