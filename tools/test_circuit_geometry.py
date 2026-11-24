import importlib.util
import unittest


@unittest.skipUnless(importlib.util.find_spec('numpy'),'Optional video dependency numpy required')
class CircuitGeometryTests(unittest.TestCase):
    def test_alignment_recovers_scale_rotation_and_translation(self):
        import numpy as np
        from circuit_geometry import fit_outline
        source=np.array([[0.,0.],[5.,0.],[6.,2.],[1.,4.],[0.,0.]])
        rotation=np.array([[0.,-1.],[1.,0.]])
        target=source@rotation*3+[100.,-20.]
        error,r,scale,offset=fit_outline(source,target)
        self.assertLess(error,1e-8)
        np.testing.assert_allclose(source@r*scale+offset,target,atol=1e-7)

    def test_unknown_circuit_has_no_invented_pit(self):
        from circuit_geometry import mapped_pit
        self.assertIsNone(mapped_pit({'session':{'location':'unknown'}},[[0,0]]*12))


if __name__=='__main__':unittest.main()
