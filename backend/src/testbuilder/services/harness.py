"""LeetCode-style code harness.

A coding question carries a typed *signature* (function name, parameters, return
type). From that we generate, per language:
  * starter code — the empty ``Solution`` stub the candidate fills in
  * a hidden driver — reads the arguments (one JSON value per line, LeetCode
    style), calls the candidate's function, and prints the return value as JSON

Comparison is done structurally in the backend (parse the driver's JSON output
and compare to the expected value) so cross-language number/format differences
never cause false failures.

Python and JavaScript are fully supported. Java and C++ drivers cover the common
DSA type subset: scalars, 1-D arrays, and ``int[][]``.
"""

import json

# canonical types accepted in a signature
SCALARS = {"int", "long", "double", "bool", "string"}
ARRAYS_1D = {"int[]", "long[]", "double[]", "bool[]", "string[]"}
ARRAYS_2D = {"int[][]", "long[][]", "double[][]", "string[][]"}
SUPPORTED_TYPES = SCALARS | ARRAYS_1D | ARRAYS_2D

# which languages can execute a given type (py/js handle everything via JSON)
_JAVA_CPP_TYPES = SCALARS | ARRAYS_1D | {"int[][]", "long[][]"}
LANGUAGES = ("python", "javascript", "java", "cpp")


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def validate_signature(signature: dict | None) -> list[str]:
    errors: list[str] = []
    if not isinstance(signature, dict):
        return ["coding question requires a 'signature' object"]
    if not signature.get("function_name"):
        errors.append("signature.function_name is required")
    params = signature.get("params")
    if not isinstance(params, list) or not params:
        errors.append("signature.params must be a non-empty list")
        params = []
    for i, param in enumerate(params):
        if not isinstance(param, dict) or not param.get("name"):
            errors.append(f"signature.params[{i}].name is required")
        if param.get("type") not in SUPPORTED_TYPES:
            errors.append(
                f"signature.params[{i}].type must be one of {sorted(SUPPORTED_TYPES)}"
            )
    if signature.get("return_type") not in SUPPORTED_TYPES:
        errors.append(f"signature.return_type must be one of {sorted(SUPPORTED_TYPES)}")
    return errors


def languages_supporting(signature: dict) -> list[str]:
    """Languages whose driver can execute this signature's types."""
    types = {p.get("type") for p in signature.get("params", [])}
    types.add(signature.get("return_type"))
    out = ["python", "javascript"]
    if types <= _JAVA_CPP_TYPES:
        out += ["java", "cpp"]
    return out


# --------------------------------------------------------------------------- #
# per-language type rendering
# --------------------------------------------------------------------------- #
_PY_HINTS = {
    "int": "int", "long": "int", "double": "float", "bool": "bool", "string": "str",
    "int[]": "List[int]", "long[]": "List[int]", "double[]": "List[float]",
    "bool[]": "List[bool]", "string[]": "List[str]",
    "int[][]": "List[List[int]]", "long[][]": "List[List[int]]",
    "double[][]": "List[List[float]]", "string[][]": "List[List[str]]",
}
_JS_HINTS = {
    "int": "number", "long": "number", "double": "number", "bool": "boolean",
    "string": "string", "int[]": "number[]", "long[]": "number[]",
    "double[]": "number[]", "bool[]": "boolean[]", "string[]": "string[]",
    "int[][]": "number[][]", "long[][]": "number[][]", "double[][]": "number[][]",
    "string[][]": "string[][]",
}
_JAVA_TYPES = {
    "int": "int", "long": "long", "double": "double", "bool": "boolean",
    "string": "String", "int[]": "int[]", "long[]": "long[]", "double[]": "double[]",
    "bool[]": "boolean[]", "string[]": "String[]", "int[][]": "int[][]",
    "long[][]": "long[][]",
}
_CPP_TYPES = {
    "int": "int", "long": "long long", "double": "double", "bool": "bool",
    "string": "string", "int[]": "vector<int>", "long[]": "vector<long long>",
    "double[]": "vector<double>", "bool[]": "vector<bool>",
    "string[]": "vector<string>", "int[][]": "vector<vector<int>>",
    "long[][]": "vector<vector<long long>>",
}


# --------------------------------------------------------------------------- #
# starter code
# --------------------------------------------------------------------------- #
def starter_code(signature: dict, language: str) -> str:
    name = signature["function_name"]
    params = signature["params"]
    ret = signature["return_type"]
    if language == "python":
        args = ", ".join(f"{p['name']}: {_PY_HINTS[p['type']]}" for p in params)
        return (
            "from typing import List\n\n"
            "class Solution:\n"
            f"    def {name}(self, {args}) -> {_PY_HINTS[ret]}:\n"
            "        # Write your solution logic here\n"
            "        pass\n"
        )
    if language == "javascript":
        doc = "\n".join(f" * @param {{{_JS_HINTS[p['type']]}}} {p['name']}" for p in params)
        names = ", ".join(p["name"] for p in params)
        return (
            "/**\n"
            f"{doc}\n"
            f" * @return {{{_JS_HINTS[ret]}}}\n"
            " */\n"
            f"var {name} = function({names}) {{\n"
            "    // Write your solution logic here\n"
            "};\n"
        )
    if language == "java":
        args = ", ".join(f"{_JAVA_TYPES[p['type']]} {p['name']}" for p in params)
        return (
            "class Solution {\n"
            f"    public {_JAVA_TYPES[ret]} {name}({args}) {{\n"
            "        // Write your solution logic here\n"
            "    }\n"
            "}\n"
        )
    if language == "cpp":
        args = ", ".join(f"{_CPP_TYPES[p['type']]} {p['name']}" for p in params)
        return (
            "class Solution {\n"
            "public:\n"
            f"    {_CPP_TYPES[ret]} {name}({args}) {{\n"
            "        // Write your solution logic here\n"
            "    }\n"
            "};\n"
        )
    raise ValueError(f"unsupported language {language}")


def starter_code_all(signature: dict) -> dict[str, str]:
    return {lang: starter_code(signature, lang) for lang in languages_supporting(signature)}


def autofill_coding_config(config: dict) -> dict:
    """Fill starter_code and allowed_languages from the signature so authors and
    the AI only need to supply the signature. Restricts allowed languages to the
    ones whose driver can execute the signature's types."""
    signature = config.get("signature")
    if not signature or validate_signature(signature):
        return config
    supported = languages_supporting(signature)
    requested = config.get("allowed_languages") or supported
    config["allowed_languages"] = [
        lang for lang in requested if lang in supported
    ] or supported
    starter = dict(config.get("starter_code") or {})
    for lang in config["allowed_languages"]:
        starter.setdefault(lang, starter_code(signature, lang))
    config["starter_code"] = starter
    config.setdefault("time_limit_ms", 5000)
    config.setdefault("memory_limit_kb", 256000)
    config.setdefault("show_case_results", "visible_only")
    return config


# --------------------------------------------------------------------------- #
# drivers (appended after the candidate's code)
# --------------------------------------------------------------------------- #
def _python_driver(signature: dict) -> str:
    n = len(signature["params"])
    name = signature["function_name"]
    return (
        "\n\n# === TestBuilder harness (do not edit) ===\n"
        "import json as _tb_json, sys as _tb_sys\n"
        "def _tb_main():\n"
        "    _lines = _tb_sys.stdin.read().split('\\n')\n"
        f"    _args = [_tb_json.loads(_lines[_i]) for _i in range({n})]\n"
        f"    _res = Solution().{name}(*_args)\n"
        "    print(_tb_json.dumps(_res, separators=(',', ':'), ensure_ascii=False))\n"
        "_tb_main()\n"
    )


def _javascript_driver(signature: dict) -> str:
    n = len(signature["params"])
    name = signature["function_name"]
    return (
        "\n\n// === TestBuilder harness (do not edit) ===\n"
        "(function(){\n"
        "  const _lines = require('fs').readFileSync(0,'utf8').split('\\n');\n"
        "  const _args = [];\n"
        f"  for (let _i=0; _i<{n}; _i++) _args.push(JSON.parse(_lines[_i]));\n"
        f"  const _res = {name}(..._args);\n"
        "  process.stdout.write(JSON.stringify(_res));\n"
        "})();\n"
    )


def _java_parse_expr(tp: str, var: str) -> str:
    """Java expression parsing one input line `var` (a JSON value) into `tp`."""
    if tp in ("int",):
        return f"Integer.parseInt({var}.trim())"
    if tp == "long":
        return f"Long.parseLong({var}.trim())"
    if tp == "double":
        return f"Double.parseDouble({var}.trim())"
    if tp == "bool":
        return f"Boolean.parseBoolean({var}.trim())"
    if tp == "string":
        return f"_tbStr({var})"
    if tp in ("int[]", "long[]", "double[]", "bool[]", "string[]"):
        return f"_tbArr_{tp[:-2]}({var})"
    if tp in ("int[][]", "long[][]"):
        return f"_tbArr2_{tp[:-4]}({var})"
    raise ValueError(tp)


def _java_driver(signature: dict) -> str:
    params = signature["params"]
    name = signature["function_name"]
    reads = []
    call_args = []
    for i, p in enumerate(params):
        reads.append(
            f"        {_JAVA_TYPES[p['type']]} a{i} = {_java_parse_expr(p['type'], f'L[{i}]')};"
        )
        call_args.append(f"a{i}")
    body = "\n".join(reads)
    call = f"new Solution().{name}({', '.join(call_args)})"
    return (
        "\n\n// === TestBuilder harness (do not edit) ===\n"
        "class Main {\n"
        "    static String _tbStr(String s){ s=s.trim(); if(s.startsWith(\"\\\"\"))"
        " s=s.substring(1,s.length()-1); return s.replace(\"\\\\\\\"\",\"\\\"\"); }\n"
        "    static int[] _tbArr_int(String s){ s=s.trim().replaceAll(\"[\\\\[\\\\] ]\",\"\");"
        " if(s.isEmpty())return new int[0]; String[] p=s.split(\",\");"
        " int[] r=new int[p.length]; for(int i=0;i<p.length;i++)r[i]=Integer.parseInt(p[i]);"
        " return r; }\n"
        "    static long[] _tbArr_long(String s){ s=s.trim().replaceAll(\"[\\\\[\\\\] ]\",\"\");"
        " if(s.isEmpty())return new long[0]; String[] p=s.split(\",\");"
        " long[] r=new long[p.length]; for(int i=0;i<p.length;i++)r[i]=Long.parseLong(p[i]);"
        " return r; }\n"
        "    static double[] _tbArr_double(String s){ s=s.trim().replaceAll(\"[\\\\[\\\\] ]\",\"\");"
        " if(s.isEmpty())return new double[0]; String[] p=s.split(\",\");"
        " double[] r=new double[p.length]; for(int i=0;i<p.length;i++)r[i]=Double.parseDouble(p[i]);"
        " return r; }\n"
        "    static boolean[] _tbArr_bool(String s){ s=s.trim().replaceAll(\"[\\\\[\\\\] ]\",\"\");"
        " if(s.isEmpty())return new boolean[0]; String[] p=s.split(\",\");"
        " boolean[] r=new boolean[p.length]; for(int i=0;i<p.length;i++)r[i]=Boolean.parseBoolean(p[i]);"
        " return r; }\n"
        "    static String[] _tbArr_string(String s){ s=s.trim();"
        " s=s.substring(1,s.length()-1); if(s.isEmpty())return new String[0];"
        " String[] p=s.split(\",\"); for(int i=0;i<p.length;i++)p[i]=_tbStr(p[i]); return p; }\n"
        "    static int[][] _tbArr2_int(String s){ s=s.trim(); s=s.substring(1,s.length()-1);"
        " if(s.isEmpty())return new int[0][]; java.util.List<int[]> rows=new java.util.ArrayList<>();"
        " int d=0,st=0; for(int i=0;i<s.length();i++){char c=s.charAt(i); if(c=='[')d++;"
        " else if(c==']'){d--; if(d==0){rows.add(_tbArr_int(s.substring(st,i+1)));}}"
        " else if(c==','&&d==0)st=i+1;} return rows.toArray(new int[0][]); }\n"
        "    static long[][] _tbArr2_long(String s){ s=s.trim(); s=s.substring(1,s.length()-1);"
        " if(s.isEmpty())return new long[0][]; java.util.List<long[]> rows=new java.util.ArrayList<>();"
        " int d=0,st=0; for(int i=0;i<s.length();i++){char c=s.charAt(i); if(c=='[')d++;"
        " else if(c==']'){d--; if(d==0){rows.add(_tbArr_long(s.substring(st,i+1)));}}"
        " else if(c==','&&d==0)st=i+1;} return rows.toArray(new long[0][]); }\n"
        "    static String _tbJson(Object o){\n"
        "        if(o==null)return \"null\";\n"
        "        if(o instanceof String)return \"\\\"\"+((String)o).replace(\"\\\"\",\"\\\\\\\"\")+\"\\\"\";\n"
        "        if(o instanceof int[]){int[] a=(int[])o; StringBuilder b=new StringBuilder(\"[\");"
        " for(int i=0;i<a.length;i++){if(i>0)b.append(\",\");b.append(a[i]);} return b.append(\"]\").toString();}\n"
        "        if(o instanceof long[]){long[] a=(long[])o; StringBuilder b=new StringBuilder(\"[\");"
        " for(int i=0;i<a.length;i++){if(i>0)b.append(\",\");b.append(a[i]);} return b.append(\"]\").toString();}\n"
        "        if(o instanceof double[]){double[] a=(double[])o; StringBuilder b=new StringBuilder(\"[\");"
        " for(int i=0;i<a.length;i++){if(i>0)b.append(\",\");b.append(a[i]);} return b.append(\"]\").toString();}\n"
        "        if(o instanceof boolean[]){boolean[] a=(boolean[])o; StringBuilder b=new StringBuilder(\"[\");"
        " for(int i=0;i<a.length;i++){if(i>0)b.append(\",\");b.append(a[i]);} return b.append(\"]\").toString();}\n"
        "        if(o instanceof String[]){String[] a=(String[])o; StringBuilder b=new StringBuilder(\"[\");"
        " for(int i=0;i<a.length;i++){if(i>0)b.append(\",\");b.append(_tbJson(a[i]));} return b.append(\"]\").toString();}\n"
        "        if(o instanceof int[][]){int[][] a=(int[][])o; StringBuilder b=new StringBuilder(\"[\");"
        " for(int i=0;i<a.length;i++){if(i>0)b.append(\",\");b.append(_tbJson(a[i]));} return b.append(\"]\").toString();}\n"
        "        if(o instanceof long[][]){long[][] a=(long[][])o; StringBuilder b=new StringBuilder(\"[\");"
        " for(int i=0;i<a.length;i++){if(i>0)b.append(\",\");b.append(_tbJson(a[i]));} return b.append(\"]\").toString();}\n"
        "        if(o instanceof Boolean||o instanceof Integer||o instanceof Long||o instanceof Double)"
        "return o.toString();\n"
        "        return o.toString();\n"
        "    }\n"
        "    public static void main(String[] args) throws Exception {\n"
        "        java.io.BufferedReader br=new java.io.BufferedReader("
        "new java.io.InputStreamReader(System.in));\n"
        "        java.util.List<String> _l=new java.util.ArrayList<>(); String _ln;\n"
        "        while((_ln=br.readLine())!=null)_l.add(_ln);\n"
        "        String[] L=_l.toArray(new String[0]);\n"
        f"{body}\n"
        f"        System.out.print(_tbJson({call}));\n"
        "    }\n"
        "}\n"
    )


def _cpp_parse(tp: str, idx: int) -> str:
    if tp == "int":
        return f"stoi(L[{idx}])"
    if tp == "long":
        return f"stoll(L[{idx}])"
    if tp == "double":
        return f"stod(L[{idx}])"
    if tp == "bool":
        return f"(L[{idx}].find(\"true\")!=string::npos)"
    if tp == "string":
        return f"_tbStr(L[{idx}])"
    if tp in ("int[]", "long[]", "double[]", "bool[]", "string[]"):
        return f"_tbArr_{tp[:-2]}(L[{idx}])"
    if tp in ("int[][]", "long[][]"):
        return f"_tbArr2_{tp[:-4]}(L[{idx}])"
    raise ValueError(tp)


def _cpp_prelude() -> str:
    # must precede the candidate's Solution class so it can use vector/string
    return "#include <bits/stdc++.h>\nusing namespace std;\n\n"


def _cpp_driver(signature: dict) -> str:
    params = signature["params"]
    name = signature["function_name"]
    call_args = ", ".join(_cpp_parse(p["type"], i) for i, p in enumerate(params))
    return (
        "\n\n// === TestBuilder harness (do not edit) ===\n"
        "static string _tbStr(string s){ if(!s.empty()&&s.front()=='\"')"
        "s=s.substr(1,s.size()-2); return s; }\n"
        "static vector<string> _split(string s){ if(!s.empty()&&s.front()=='[')"
        "s=s.substr(1,s.size()-2); vector<string> r; string cur; int d=0;"
        " for(char c: s){ if(c=='[')d++; if(c==']')d--; if(c==','&&d==0){r.push_back(cur);cur=\"\";}"
        " else cur+=c;} if(!cur.empty()||!r.empty())r.push_back(cur); return r; }\n"
        "static vector<int> _tbArr_int(string s){ vector<int> r; for(auto&x:_split(s))"
        "if(!x.empty())r.push_back(stoi(x)); return r; }\n"
        "static vector<long long> _tbArr_long(string s){ vector<long long> r; for(auto&x:_split(s))"
        "if(!x.empty())r.push_back(stoll(x)); return r; }\n"
        "static vector<double> _tbArr_double(string s){ vector<double> r; for(auto&x:_split(s))"
        "if(!x.empty())r.push_back(stod(x)); return r; }\n"
        "static vector<bool> _tbArr_bool(string s){ vector<bool> r; for(auto&x:_split(s))"
        "if(!x.empty())r.push_back(x.find(\"true\")!=string::npos); return r; }\n"
        "static vector<string> _tbArr_string(string s){ vector<string> r; for(auto&x:_split(s))"
        "r.push_back(_tbStr(x)); return r; }\n"
        "static vector<vector<int>> _tbArr2_int(string s){ if(!s.empty()&&s.front()=='[')"
        "s=s.substr(1,s.size()-2); vector<vector<int>> r; string cur; int d=0;"
        " for(char c: s){ if(c=='[')d++; if(c==']'){d--; cur+=c; if(d==0){r.push_back(_tbArr_int(cur));cur=\"\";} continue;}"
        " if(c==','&&d==0)continue; cur+=c;} return r; }\n"
        "static vector<vector<long long>> _tbArr2_long(string s){ if(!s.empty()&&s.front()=='[')"
        "s=s.substr(1,s.size()-2); vector<vector<long long>> r; string cur; int d=0;"
        " for(char c: s){ if(c=='[')d++; if(c==']'){d--; cur+=c; if(d==0){r.push_back(_tbArr_long(cur));cur=\"\";} continue;}"
        " if(c==','&&d==0)continue; cur+=c;} return r; }\n"
        "static string _tbJson(int v){return to_string(v);}\n"
        "static string _tbJson(long long v){return to_string(v);}\n"
        "static string _tbJson(double v){ ostringstream o; o<<v; return o.str(); }\n"
        "static string _tbJson(bool v){return v?\"true\":\"false\";}\n"
        "static string _tbJson(const string&v){return \"\\\"\"+v+\"\\\"\";}\n"
        "template<class T> static string _tbJson(const vector<T>&a){ string r=\"[\";"
        " for(size_t i=0;i<a.size();i++){ if(i)r+=\",\"; r+=_tbJson(a[i]); } return r+\"]\"; }\n"
        "int main(){ vector<string> L; string ln; while(getline(cin,ln))L.push_back(ln);\n"
        f"    cout<<_tbJson(Solution().{name}({call_args})); return 0; }}\n"
    )


_DRIVERS = {
    "python": _python_driver,
    "javascript": _javascript_driver,
    "java": _java_driver,
    "cpp": _cpp_driver,
}


def build_program(signature: dict, language: str, candidate_code: str) -> str:
    driver = _DRIVERS.get(language)
    if driver is None:
        raise ValueError(f"unsupported language {language}")
    prelude = _cpp_prelude() if language == "cpp" else ""
    return prelude + candidate_code.rstrip() + driver(signature)


# --------------------------------------------------------------------------- #
# I/O helpers
# --------------------------------------------------------------------------- #
def stdin_for_args(args: list) -> str:
    """One JSON value per line, in parameter order (LeetCode convention)."""
    return "\n".join(json.dumps(a, separators=(",", ":"), ensure_ascii=False) for a in args)


def parse_custom_input(text: str, n_params: int) -> list | None:
    """Parse a candidate's custom-input box (one JSON value per line) into args."""
    lines = [ln for ln in text.split("\n") if ln.strip() != ""]
    if len(lines) < n_params:
        return None
    try:
        return [json.loads(ln) for ln in lines[:n_params]]
    except json.JSONDecodeError:
        return None


def _norm(value):
    """Normalize for structural comparison: tuples->lists, ints/floats compared
    with tolerance handled separately."""
    if isinstance(value, list):
        return [_norm(v) for v in value]
    return value


def outputs_equal(produced_json: str, expected) -> bool:
    """Structurally compare the driver's JSON stdout to the expected value."""
    produced_json = (produced_json or "").strip()
    try:
        produced = json.loads(produced_json)
    except (json.JSONDecodeError, ValueError):
        return False
    return _deep_equal(_norm(produced), _norm(expected))


def _deep_equal(a, b, *, tol: float = 1e-6) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        # bool is only equal to bool (never to 0/1)
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tol
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_deep_equal(x, y, tol=tol) for x, y in zip(a, b, strict=False))
    return a == b
