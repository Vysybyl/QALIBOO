//
// Created by kanthavel on 26/04/23.
//
#include "Python.h"  // NOLINT(build/include)

#include <string>  // NOLINT(build/include_order)

#include "gpp_my_class.hpp"
#include <boost/python/def.hpp>  // NOLINT(build/include_order)
#include <boost/python/class.hpp>  // NOLINT(build/include_order)
#include <boost/python/list.hpp>  // NOLINT(build/include_order)
#include <boost/python/make_constructor.hpp>  // NOLINT(build/include_order)

namespace optimal_learning {

    namespace {  // unnamed namespace
        struct World
        {
            World(std::string msg): msg(msg) {}
            void set(std::string msg) { this->msg = msg; }
            std::string greet() { return msg; }
            std::string msg;
        };

    }

    void ExportMyClassFunctions() {
        boost::python::class_<World, boost::noncopyable>("World", boost::python::init<std::string>())
                .def("greet", &World::greet)
                .def("set", &World::set)
                ;
    }
}