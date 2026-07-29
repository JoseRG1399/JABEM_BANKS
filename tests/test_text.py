from app.utils.text import extract_digit_blocks, normalize_compact, normalize_text


def test_normalize_text_removes_accents_and_uppercases():
    original = "Iva tasa de desc débito/179064102 Terminales Punto de Venta"
    expected = "IVA TASA DE DESC DEBITO 179064102 TERMINALES PUNTO DE VENTA"
    assert normalize_text(original) == expected


def test_normalize_text_collapses_repeated_spaces():
    assert normalize_text("HOLA    MUNDO") == "HOLA MUNDO"


def test_normalize_text_empty():
    assert normalize_text("") == ""
    assert normalize_text(None) == ""


def test_normalize_text_preserves_numbers():
    assert normalize_text("REF-00123456") == "REF 00123456"


def test_normalize_compact_removes_spaces():
    assert normalize_compact("VENTAS DEBITO 4102") == "VENTASDEBITO4102"


def test_extract_digit_blocks():
    assert extract_digit_blocks("VENTAS DEBITO/149064102 TERMINALES") == ["149064102"]
    assert extract_digit_blocks("SIN NUMEROS") == []
