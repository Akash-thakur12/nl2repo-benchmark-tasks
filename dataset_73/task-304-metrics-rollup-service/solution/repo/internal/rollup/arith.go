package rollup

// Arithmetic the specification asks for, which is not the arithmetic Go gives
// you by default: `/` truncates toward zero and math.Round sends exact halves
// away from zero. Both are wrong here.

// floorDiv divides rounding toward negative infinity.
func floorDiv(a, b int64) int64 {
	q := a / b
	if (a%b != 0) && ((a < 0) != (b < 0)) {
		q--
	}
	return q
}

// floorMod is the remainder that pairs with floorDiv, so it always carries the
// sign of the divisor.
func floorMod(a, b int64) int64 {
	return a - floorDiv(a, b)*b
}

// windowStart implements spec 2.2 and 2.3: half-open windows, so a sample
// exactly on a boundary starts the window rather than closing the previous one.
func windowStart(t, seconds int64) int64 {
	return floorDiv(t, seconds) * seconds
}

// roundHalfEven implements spec 3.2.2: nearest integer, with an exact half going
// to the even neighbour. 5/2 is 2, 7/2 is 4 and -5/2 is -2.
func roundHalfEven(numerator, denominator int64) int64 {
	quotient := floorDiv(numerator, denominator)
	remainder := floorMod(numerator, denominator)
	twice := 2 * remainder
	switch {
	case twice > denominator:
		return quotient + 1
	case twice < denominator:
		return quotient
	default:
		if quotient%2 != 0 {
			return quotient + 1
		}
		return quotient
	}
}
